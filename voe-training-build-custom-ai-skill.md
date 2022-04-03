# Build a custom AI Skill on your IP camera

This article describes how you can build a custom AI Skill on your IP camera using Vision on Edge (VoE). 

VoE is an open-source accelerator that you can use to build vision-based intelligent edge solutions using Machine Learning (ML) quickly and easily. It can help you get insights and actions from a Real Time Streaming Protocol (RTSP) Internet Protocol (IP) camera using a no-code user interface (UI) that runs and processes streams locally on your Edge device.

## Prerequisites

- VoE
- An RTSP IP camera
- An Edge device 

## Install an RTSP IP camera

One of the most critical steps is to select an RTSP IP camera that can capture and present images that artificial intelligence (AI) or machine learning (ML) models can evaluate and identify correctly. 

1. Select the type of camera that fits your needs
2. Follow the manufacturer’s instructions to install the camera.
3. Test your camera to ensure it’s working correctly.

## Create an AI Skill project

VOE enables you to build and deploy custom computer vision solutions without using any coding. The first step is to create your project.

1. Start VOE.
2. On the **Overview** page, select the **Demos & tutorials** tab, and then select **Create a vision prototype**.
3. On the **New VoE prototype** page:

     1. In the **Project** name box, enter a name for the prototype.
     1. In the **Project description** box, enter a brief description for the prototype.
     1. From the **Device type** dropdown, select **VoE**.
     1. From the **Resource** dropdown, select a resource. 
        or 
        Select **Create a new resource**, and in the **Create** window:

          1. Enter a name for your new resource.
          2. Select your Azure subscription.
          3. Select a resource group or create a new one.
          4. Select your preferred region.
          5. Select your pricing tier (we recommend S0).
          6. Select **Create**.
          
     1. Under **Project type**, choose **Perform object detection** or **Perform image classification**.
     
          For more information on the project types, select **Help me choose**.
     1. Under **Optimization**, choose to optimize the project for **Accuracy**, **Low network latency**, or **A balance of both**.
     1. Select **Create**.

## Next steps
- To add a device to your project, select [Connect a device to your project and capture]().
- To add labels to your images and train your model, select [Tag images and train your model]().
- To deploy your model, select [Deploy your AI model]().
