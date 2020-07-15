"""
Camera models
"""
import datetime
import json
import logging
# import queue
# import random
import sys
import threading
import time
from io import BytesIO

import cv2
import requests
from azure.cognitiveservices.vision.customvision.training import \
    CustomVisionTrainingClient
# from azure.cognitiveservices.vision.customvision.training.models import (
# ImageFileCreateEntry, Region)
from azure.cognitiveservices.vision.customvision.training.models.custom_vision_error_py3 import \
    CustomVisionErrorException
from azure.iot.device import IoTHubModuleClient
from django.core import files
from django.db import models
from django.db.models.signals import post_save, pre_save
# from django.db.models.signals import post_delete, m2m_changed
from django.db.utils import IntegrityError
from PIL import Image as PILImage
from rest_framework import status

from cameras.utils.app_insight import (get_app_insight_logger, img_monitor,
                                       part_monitor, retraining_job_monitor,
                                       training_job_monitor)
from configs.iot_config import IOT_HUB_CONNECTION_STRING
from azure_settings.models import Setting
from locations.models import Location

logger = logging.getLogger(__name__)

try:
    iot = IoTHubRegistryManager(IOT_HUB_CONNECTION_STRING)
except:
    iot = None


def is_edge():
    """Determine is edge or not. Return bool"""
    try:
        IoTHubModuleClient.create_from_edge_environment()
        return True
    except:
        return False


def inference_module_url():
    """Return Inference URL"""
    if is_edge():
        return "172.18.0.1:5000"
    return "localhost:5000"


# Create your models here.


class Part(models.Model):
    """Part Model"""

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000, blank=True, default="")
    is_demo = models.BooleanField(default=False)
    name_lower = models.CharField(max_length=200, default=str(name).lower())

    class Meta:
        unique_together = ("name_lower", "is_demo")

    def __str__(self):
        return self.name

    @staticmethod
    def pre_save(instance, update_fields, **kwargs):
        """Part pre_save"""
        try:
            update_fields = []
            instance.name_lower = str(instance.name).lower()
            update_fields.append("name_lower")
        except IntegrityError as integrity_error:
            logger.error(integrity_error)
            raise integrity_error
        except:
            logger.exception("Unexpected Error in Part Presave")


class Image(models.Model):
    """Image Model"""

    image = models.ImageField(upload_to="images/")
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    labels = models.CharField(max_length=1000, null=True)
    is_relabel = models.BooleanField(default=False)
    confidence = models.FloatField(default=0.0)
    uploaded = models.BooleanField(default=False)
    remote_url = models.CharField(max_length=1000, null=True)

    def get_remote_image(self):
        """Download image using remote url"""
        try:
            if self.remote_url:
                resp = requests.get(self.remote_url)
                if resp.status_code != status.HTTP_200_OK:
                    raise requests.exceptions.RequestException
                fp = BytesIO()
                fp.write(resp.content)
                file_name = f"{self.part.name}-{self.remote_url.split('/')[-1]}"
                logger.info("Saving as name %s", file_name)

                self.image.save(file_name, files.File(fp))
                fp.close()
                self.save()
        except requests.exceptions.RequestException as e:
            # Probably wrong url
            raise e
        except Exception as unexpected_error:
            logger.exception("unexpected error")
            raise unexpected_error

    def set_labels(self, left: float, top: float, width: float, height: float):
        "Set label to image"
        try:
            if left > 1 or top > 1 or width > 1 or height > 1:
                raise ValueError(
                    f"{left}, {top}, {width}, {height} must be less than 1")
            elif left < 0 or top < 0 or width < 0 or height < 0:
                # raise ValueError(
                # f"{left}, {top}, {width}, {height} must be greater than 0")
                logger.error("%s, %s, %s, %s must be greater than 0", left,
                             top, width, height)
                return
            elif left + width > 1:
                logger.error("left + width: %s + %s must be less than 1", left,
                             width)
                return
            elif top + height > 1:
                logger.error("top + height: %s + %s must be less than 1", top,
                             height)
                return

            with PILImage.open(self.image) as img:
                logger.info("Successfully open img %s", self.image)
                size_width, size_height = img.size
                label_x1 = int(size_width * left)
                label_y1 = int(size_height * top)
                label_x2 = int(size_width * (left + width))
                label_y2 = int(size_height * (top + height))
                self.labels = json.dumps([{
                    "x1": label_x1,
                    "y1": label_y1,
                    "x2": label_x2,
                    "y2": label_y2
                }])
                self.save()
                logger.info("Successfully save labels to %s", self.labels)
        except ValueError as e:
            raise e
        except Exception:
            logger.exception("Set label raise unexpected error")
            raise e

    def add_labels(self, left: float, top: float, width: float, height: float):
        "Add Labels to Image"
        try:
            if left > 1 or top > 1 or width > 1 or height > 1:
                raise ValueError("%s, %s, %s, %s must be less than 1", left,
                                 top, width, height)
            elif left < 0 or top < 0 or width < 0 or height < 0:
                raise ValueError("%s, %s, %s, %s must be greater than 0", left,
                                 top, width, height)
            elif left + width > 1:
                raise ValueError("left + width: %s + %s must be less than 1",
                                 left, width)
            elif top + height > 1:
                raise ValueError("top + height: %s + %s  must be less than 1",
                                 top, height)
        except ValueError as e:
            raise e


class Annotation(models.Model):
    """Annotation Model"""

    image = models.OneToOneField(Image, on_delete=models.CASCADE)
    labels = models.CharField(max_length=1000, null=True)


class Camera(models.Model):
    """Camera Model"""

    name = models.CharField(max_length=200)
    rtsp = models.CharField(max_length=1000)
    area = models.CharField(max_length=1000, blank=True)
    is_demo = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @staticmethod
    def post_save(instance, update_fields, **kwargs):
        """Camera post_save"""
        if len(instance.area) > 1:
            logger.info("Sending new AOI to Inference Module...")
            try:
                requests.get(
                    url="http://" + inference_module_url() + "/update_cam",
                    params={
                        "cam_type": "rtsp",
                        "cam_source": instance.rtsp,
                        "aoi": instance.area,
                    },
                )
            except:
                logger.error("Request failed")


post_save.connect(Camera.post_save, Camera, dispatch_uid="Camera_post")


class Project(models.Model):
    """Project Model"""

    setting = models.ForeignKey(Setting, on_delete=models.CASCADE, default=1)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, null=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True)
    parts = models.ManyToManyField(Part, related_name="part")
    customvision_project_id = models.CharField(max_length=200,
                                               null=True,
                                               blank=True,
                                               default="")
    customvision_project_name = models.CharField(max_length=200,
                                                 null=True,
                                                 blank=True,
                                                 default="")
    download_uri = models.CharField(max_length=1000,
                                    null=True,
                                    blank=True,
                                    default="")
    needRetraining = models.BooleanField(default=True)
    accuracyRangeMin = models.IntegerField(default=30)
    accuracyRangeMax = models.IntegerField(default=80)
    maxImages = models.IntegerField(default=20)
    deployed = models.BooleanField(default=False)
    training_counter = models.IntegerField(default=0)
    retraining_counter = models.IntegerField(default=0)
    is_demo = models.BooleanField(default=False)

    metrics_is_send_iothub = models.BooleanField(default=False)
    metrics_accuracy_threshold = models.IntegerField(default=50)
    metrics_frame_per_minutes = models.IntegerField(default=6)

    prob_threshold = models.IntegerField(default=10)

    @staticmethod
    def pre_save(sender, instance, update_fields, **kwargs):
        """Project pre_save"""
        logger.info("Project pre_save")
        logger.info("Saving instance: %s %s", instance, update_fields)
        if update_fields is not None:
            return
        # if instance.id is not None:
        #    return

        trainer = instance.setting.revalidate_and_get_trainer_obj()
        if instance.is_demo:
            logger.info("Project instance.is_demo: %s", instance.is_demo)
            pass
        elif trainer and instance.customvision_project_id:
            # Endpoint and Training_key is valid, and trying to save with
            # customvision_project_id...
            logger.info("Project CustomVision Id: %s",
                        instance.customvision_project_id)
            try:
                cv_project_obj = trainer.get_project(
                    instance.customvision_project_id)
            except CustomVisionErrorException as e:
                logger.error(e)
                logger.error(
                    "Project %s not belong to Training Key + Endpoint pair." +
                    "Set Project Id to ''",
                    instance.customvision_project_id,
                )
                instance.customvision_project_id = ""
            except Exception as e:
                logger.exception("Unexpected error")
        elif trainer:
            # Endpoint and Training_key is valid, and trying to save without cv_project_id
            logger.info("Setting project name")
            try:
                if not instance.customvision_project_name:
                    raise ValueError("Use Default")
                name = instance.customvision_project_name
            except:
                name = "VisionOnEdge-" + datetime.datetime.utcnow().isoformat()
                instance.customvision_project_name = name
            logger.info("Setting project name: %s",
                        instance.customvision_project_name)

            # logger.info('Creating Project on Custom Vision')
            # project = instance.setting.create_project(name)
            # logger.info(
            #    f'Got Custom Vision Project Id: {project.id}. Saving...')
            # instance.customvision_project_id = project.id
        else:
            # logger.info('Has not set the key, Got DUMMY PRJ ID')
            # instance.customvision_project_id = 'DUMMY-PROJECT-ID'
            instance.customvision_project_id = ""
        logger.info("Project pre_save... End")

    @staticmethod
    def post_save(sender, instance, created, update_fields, **kwargs):
        """Project post_save"""
        logger.info("Project post_save")
        logger.info(f"Saving instance: {instance} {update_fields}")

        confidence_min = 30
        confidence_max = 80
        max_images = 10
        metrics_is_send_iothub = False
        metrics_accuracy_threshold = 50
        metrics_frame_per_minutes = 6

        if instance.accuracyRangeMin is not None:
            confidence_min = instance.accuracyRangeMin

        if instance.accuracyRangeMax is not None:
            confidence_max = instance.accuracyRangeMax

        if instance.maxImages is not None:
            max_images = instance.maxImages

        if instance.metrics_is_send_iothub is not None:
            metrics_is_send_iothub = instance.metrics_is_send_iothub
        if instance.metrics_accuracy_threshold is not None:
            metrics_accuracy_threshold = instance.metrics_accuracy_threshold
        if instance.metrics_frame_per_minutes is not None:
            metrics_frame_per_minutes = instance.metrics_frame_per_minutes


        def _r(confidence_min, confidence_max, max_images):
            requests.get(
                "http://" + inference_module_url() +
                "/update_retrain_parameters",
                params={
                    "confidence_min": confidence_min,
                    "confidence_max": confidence_max,
                    "max_images": max_images,
                },
            )

            requests.get('http://' + inference_module_url() +
                         '/update_iothub_parameters',
                         params={
                             'is_send': metrics_is_send_iothub,
                             'threshold': metrics_accuracy_threshold,
                             'fpm': metrics_frame_per_minutes,
                         })

        threading.Thread(target=_r,
                         args=(confidence_min, confidence_max,
                               max_images)).start()

        if update_fields is not None:
            return
        if not created:
            logger.info("Project modified")

        project_id = instance.id
        logger.info("Project post_save... End")
        # def _train_f(pid):
        #     requests.get('http://localhost:8000/api/projects/'+str(pid)+'/train')
        # t = threading.Thread(target=_train_f, args=(project_id,))
        # t.start()

    @staticmethod
    def pre_delete(sender, instance, using):
        """Pre_delete"""
        pass

    def dequeue_iterations(self, max_iterations=2):
        """Dequeue training iterations of a project"""
        try:
            trainer = self.setting.revalidate_and_get_trainer_obj()
            if not trainer:
                return
            if not self.customvision_project_id:
                return
            iterations = trainer.get_iterations(self.customvision_project_id)
            if len(iterations) > max_iterations:
                # TODO delete train in Train Model
                trainer.delete_iteration(self.customvision_project_id,
                                         iterations[-1].as_dict()["id"])
        except CustomVisionErrorException as e:
            logger.error(e)
        except:
            logger.exception("dequeue_iteration error")

    def upcreate_training_status(self,
                                 status: str,
                                 log: str,
                                 performance: str = "{}"):
        """
        A wrapper function to create or update the training status of a
        project
        """
        logger.info("Updating Training Status: %s %s", status, log)
        obj, created = Train.objects.update_or_create(
            project=self,
            defaults={
                "status": status,
                "log": log,
                "performance": performance
            },
        )
        return obj, created

    def create_project(self):
        """Create a project for local project_obj (self) on CustomVision"""
        trainer = self.setting.get_trainer_obj()
        logger.info("Creating obj detection project")
        try:
            if not self.customvision_project_name:
                self.customvision_project_name = (
                    "VisionOnEdge-" + datetime.datetime.utcnow().isoformat())
            project = trainer.create_project(
                name=self.customvision_project_name,
                domain_id=self.setting.obj_detection_domain_id,
            )
            self.customvision_project_id = project.id
            update_fields = [
                "customvision_project_id", "customvision_project_name"
            ]
            self.save(update_fields=update_fields)
        except CustomVisionErrorException as customvision_err:
            logger.error("Project create_project error %s", customvision_err)
            raise customvision_err
        except Exception as e:
            logger.exception("Project create_project: Unexpected Error")
            raise e

    def update_app_insight_counter(
            self,
            has_new_parts: bool,
            has_new_images: bool,
            source,
            parts_last_train: int,
            images_last_train: int,
    ):
        """Send message to app insight"""
        try:
            retrain = train = 0
            if has_new_parts:
                logger.info("This is a training job")
                self.training_counter += 1
                self.save(update_fields=["training_counter"])
                train = 1
            elif has_new_images:
                logger.info("This is a re-training job")
                self.retraining_counter += 1
                self.save(update_fields=["retraining_counter"])
                retrain = 1
            else:
                logger.info("Project not changed")
            logger.info("Sending Data to App Insight %s",
                        self.setting.is_collect_data)
            if self.setting.is_collect_data:

                # Metrics
                logger.info("Sending Logs to App Insight")
                part_monitor(len(Part.objects.filter(is_demo=False)))
                img_monitor(len(Image.objects.all()))
                training_job_monitor(self.training_counter)
                retraining_job_monitor(self.retraining_counter)
                trainer = self.setting.get_trainer_obj()
                images_now = trainer.get_tagged_image_count(
                    self.customvision_project_id)
                parts_now = len(trainer.get_tags(self.customvision_project_id))
                # Traces
                az_logger = get_app_insight_logger()
                az_logger.warning(
                    "training",
                    extra={
                        "custom_dimensions": {
                            "train": train,
                            "images": images_now - images_last_train,
                            "parts": parts_now - parts_last_train,
                            "retrain": retrain,
                            "source": source,
                        }
                    },
                )
        except Exception:
            logger.exception(
                "update_app_insight_counter occur unexcepted error")
            raise

    def train_project(self):
        """
        Submit training task to CustomVision. Return is training request success (boolean)
        : Success: return True
        : Failed : return False
        """
        is_task_success = False
        update_fields = []

        try:
            # Get CustomVisionClient
            trainer = self.setting.revalidate_and_get_trainer_obj()
            if not trainer:
                logger.error("Trainer is invalid. Not going to train...")
                raise

            # Submit training task to CustomVision
            logger.info(
                f"{self.customvision_project_name} submit training task to CustomVision"
            )
            trainer.train_project(self.customvision_project_id)
            # Set deployed
            self.deployed = False
            update_fields.append("deployed")
            logger.info("set deployed = False")

            # If all above is success
            is_task_success = True
            return is_task_success
        except CustomVisionErrorException as customvision_err:
            logger.error(f"From Custom Vision: {customvision_err.message}")
            raise
        except Exception:
            logger.exception("Unexpected error while Project.train_project")
            raise
        finally:
            self.save(update_fields=update_fields)

    def export_iterationv3_2(self, iteration_id):
        """
        CustomVisionTrainingClient SDK may have some issues exporting
        Use the REST API
        """
        # trainer.export_iteration(customvision_project_id,
        # iteration.id,
        # 'ONNX')
        setting_obj = self.setting
        url = (setting_obj.endpoint + "customvision/v3.2/training/projects/" +
               self.customvision_project_id + "/iterations/" + iteration_id +
               "/export?platform=ONNX")
        res = requests.post(url,
                            "{body}",
                            headers={"Training-key": setting_obj.training_key})
        return res

    def update_prob_threshold(self, prob_threshold):
        """update confidenece threshold of boundingBox
        """
        self.prob_threshold = prob_threshold

        if prob_threshold > 100 or prob_threshold < 0:
            raise ValueError('prob_threshold out of range')

        requests.get(
            "http://" + inference_module_url() + "/update_prob_threshold",
            params={
                "prob_threshold": prob_threshold,
            },
        )
        self.save(update_fields=['prob_threshold'])

    # @staticmethod
    # def m2m_changed(sender, instance, action, **kwargs):
    #    print('[INFO] M2M_CHANGED')
    #    project_id = instance.id
    #    #print(instance.parts)
    #    requests.get('http://localhost:8000/api/projects/'+str(project_id)+'/train')


class Train(models.Model):
    """Train Model"""

    status = models.CharField(max_length=200)
    log = models.CharField(max_length=1000)
    performance = models.CharField(max_length=1000, default="{}")
    project = models.ForeignKey(Project, on_delete=models.CASCADE)


class Task(models.Model):
    """Task Model"""

    task_type = models.CharField(max_length=100)
    status = models.CharField(max_length=200)
    log = models.CharField(max_length=1000)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    def start_exporting(self):
        """Start Exporting"""
        def _export_worker(self):
            """Export Model Worker"""
            project_obj = self.project
            trainer = project_obj.setting.revalidate_and_get_trainer_obj()
            customvision_project_id = project_obj.customvision_project_id
            while True:
                time.sleep(1)
                iterations = trainer.get_iterations(customvision_project_id)
                if len(iterations) == 0:
                    logger.error("failed: not yet trained")
                    self.status = "running"
                    self.log = "failed: not yet trained"
                    self.save()
                    return

                iteration = iterations[0]
                if not iteration.exportable or iteration.status != "Completed":
                    self.status = "running"
                    self.log = "Status : training model"
                    self.save()
                    continue

                exports = trainer.get_exports(customvision_project_id,
                                              iteration.id)
                if len(exports) == 0 or not exports[0].download_uri:
                    logger.info("Status: exporting model")
                    self.status = "running"
                    self.log = "Status : exporting model"
                    res = project_obj.export_iterationv3_2(iteration.id)
                    self.save()
                    logger.info(res.json())
                    continue

                logger.info(
                    "Successfully export model. download_uri: %s",
                    exports[0].download_uri,
                )
                self.status = "ok"
                self.log = "Status : work done"
                self.save()
                project_obj.download_uri = exports[0].download_uri
                project_obj.save()
                break
            return

        threading.Thread(target=_export_worker, args=(self, )).start()


pre_save.connect(Part.pre_save, Part, dispatch_uid="Part_pre")
pre_save.connect(Project.pre_save, Project, dispatch_uid="Project_pre")
post_save.connect(Project.post_save, Project, dispatch_uid="Project_post")
# m2m_changed.connect(Project.m2m_changed, Project.parts.through, dispatch_uid='Project_m2m')


# FIXME consider move this out of models.py
class Stream(object):
    """Stream Class"""
    def __init__(self, rtsp, part_id=None, inference=False):
        if rtsp == "0":
            self.rtsp = 0
        elif rtsp == "1":
            self.rtsp = 1
        else:
            self.rtsp = rtsp
        self.part_id = part_id

        self.last_active = time.time()
        self.status = "init"
        self.last_img = None
        self.cur_img_index = 0
        self.last_get_img_index = 0
        self.id = id(self)

        self.mutex = threading.Lock()
        self.predictions = []
        self.inference = inference
        self.iot = None
        try:
            self.iot = IoTHubModuleClient.create_from_edge_environment()
        except KeyError as key_error:
            logger.error(key_error)
        except OSError as os_error:
            logger.error(os_error)
        except Exception:
            logger.exception("Unexpected error")

        logger.info("inference %s", self.inference)
        logger.info("iot %s", self.iot)

        def _listener(self):
            if not self.inference:
                return
            while True:
                if self.last_active + 10 < time.time():
                    print("[INFO] stream finished")
                    break
                sys.stdout.flush()
                res = requests.get("http://" + inference_module_url() +
                                   "/prediction")

                self.mutex.acquire()
                self.predictions = res.json()
                self.mutex.release()
                time.sleep(0.02)
                # print('received p', self.predictions)

                # inference = self.iot.receive_message_on_input('inference', timeout=1)
                # if not inference:
                #    self.mutex.acquire()
                #    self.bboxes = []
                #    self.mutex.release()
                # else:
                #    data = json.loads(inference.data)
                #    print('receive inference', data)
                #    self.mutex.acquire()
                #    self.bboxes = [{
                #        'label': data['Label'],
                #        'confidence': data['Confidence'] + '%',
                #        'p1': (data['Position'][0], data['Position'][1]),
                #        'p2': (data['Position'][2], data['Position'][3])
                #    }]
                #    self.mutex.release()

        # if self.iot:
        threading.Thread(target=_listener, args=(self, )).start()

    def gen(self):
        """generator for stream"""
        self.status = "running"
        logger.info(f"start streaming with {self.rtsp}")
        self.cap = cv2.VideoCapture(self.rtsp)
        while self.status == "running":
            if not self.cap.isOpened():
                raise ValueError("Cannot connect to rtsp")
            t, img = self.cap.read()
            # Need to add the video flag FIXME
            if t == False:
                self.cap = cv2.VideoCapture(self.rtsp)
                time.sleep(1)
                continue

            img = cv2.resize(img, None, fx=0.5, fy=0.5)
            self.last_active = time.time()
            self.last_img = img.copy()
            self.cur_img_index = (self.cur_img_index + 1) % 10000
            self.mutex.acquire()
            predictions = list(prediction.copy()
                               for prediction in self.predictions)
            self.mutex.release()

            # print('bboxes', bboxes)
            # cv2.rectangle(img, bbox['p1'], bbox['p2'], (0, 0, 255), 3)
            # cv2.putText(img, bbox['label'] + ' ' + bbox['confidence'],
            # (bbox['p1'][0], bbox['p1'][1]-15),
            # cv2.FONT_HERSHEY_COMPLEX,
            # 0.6,
            # (0, 0, 255),
            # 1)
            height, width = img.shape[0], img.shape[1]
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1
            thickness = 3
            for prediction in predictions:
                if prediction["probability"] > 0.25:
                    x1 = int(prediction["boundingBox"]["left"] * width)
                    y1 = int(prediction["boundingBox"]["top"] * height)
                    x2 = x1 + int(prediction["boundingBox"]["width"] * width)
                    y2 = y1 + int(prediction["boundingBox"]["height"] * height)
                    img = cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255),
                                        2)
                    img = cv2.putText(
                        img,
                        prediction["tagName"],
                        (x1 + 10, y1 + 30),
                        font,
                        font_scale,
                        (0, 0, 255),
                        thickness,
                    )
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" +
                   cv2.imencode(".jpg", img)[1].tobytes() + b"\r\n")
        self.cap.release()

    def get_frame(self):
        """Get frame"""
        print("[INFO] get frame", self)
        # b, img = self.cap.read()
        time_begin = time.time()
        while True:
            if time.time() - time_begin > 5:
                break
            if self.last_get_img_index == self.cur_img_index:
                time.sleep(0.01)
            else:
                break
        self.last_get_img_index = self.cur_img_index
        img = self.last_img.copy()
        # if b: return cv2.imencode('.jpg', img)[1].tobytes()
        # else : return None
        return cv2.imencode(".jpg", img)[1].tobytes()

    def close(self):
        """close stream"""
        self.status = "stopped"
        logger.info(f"release {self}")