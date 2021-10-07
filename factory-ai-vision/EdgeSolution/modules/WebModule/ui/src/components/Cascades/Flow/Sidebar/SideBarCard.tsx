import React, { useCallback } from 'react';
import { Stack, Text, Label, Link, IContextualMenuProps, IconButton } from '@fluentui/react';

import { TrainingProject, NodeType } from '../../../../store/trainingProjectSlice';
import { getClasses } from './style';
import { getNodeImage } from '../../utils';
import { convertProjectType } from '../../../utils';

interface Props {
  model: TrainingProject;
  type: NodeType;
}

const isDraggableModel = (model: TrainingProject) => model.classification_type !== 'Multilabel';

const Model = (props: Props) => {
  const { model, type } = props;

  const classes = getClasses();

  const onDragStart = useCallback((event, nodeType, selectId) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('id', selectId);
    event.dataTransfer.effectAllowed = 'move';
  }, []);

  const menuProps: IContextualMenuProps = {
    items: [
      {
        key: 'properties',
        text: 'Properties',
        iconProps: { iconName: 'Equalizer' },
      },
      {
        key: 'delete',
        text: 'Delete',
        iconProps: { iconName: 'Delete' },
      },
    ],
  };

  return (
    <>
      <Stack
        onDragStart={(event) => onDragStart(event, type, model.id)}
        draggable={isDraggableModel(model)}
        styles={{ root: classes.root }}
      >
        {model.classification_type === 'Multilabel' && <Stack className={classes.disableCover} />}
        <Stack horizontal>
          <img style={{ height: '60px', width: '60px' }} src={getNodeImage(type)} alt="icon" />
          <Stack styles={{ root: classes.titleWrapper }} horizontal horizontalAlign="space-between">
            {type === 'sink' ? (
              <Stack>
                <Label styles={{ root: classes.title }}>Export</Label>
              </Stack>
            ) : (
              <Stack>
                <Label styles={{ root: classes.title }}>{model.name}</Label>
                <Text styles={{ root: classes.label }}>{convertProjectType(model.projectType)}</Text>
              </Stack>
            )}
            <Stack verticalAlign="center">
              <IconButton
                className={classes.controlBtn}
                menuProps={menuProps}
                menuIconProps={{ iconName: 'MoreVertical' }}
              />
            </Stack>
          </Stack>
        </Stack>
        <Stack styles={{ root: classes.bottomWrapper }}>
          {type === 'openvino_model' && <Label styles={{ root: classes.smallLabel }}>By Intel</Label>}
          {type === 'customvision_model' && (
            <Label styles={{ root: classes.smallLabel }}>By Microsoft Custom Vision</Label>
          )}
          <Link styles={{ root: classes.addLabel }}>add</Link>
        </Stack>
      </Stack>
    </>
  );
};

export default Model;