import React from 'react';
import {Composition} from 'remotion';
import {KhyratLegalReel, ReelProps} from './Reel';

const defaults: ReelProps = {
  scenes: [],
  voiceAudio: '',
  sloganAudio: '',
  logo: '',
  subtitles: [],
  voiceFrames: 900,
  totalFrames: 1080,
  fps: 30,
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="KhyratLegalReel"
    component={KhyratLegalReel}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={1080}
    defaultProps={defaults}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(1, props.totalFrames),
    })}
  />
);
