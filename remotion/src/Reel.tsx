import React from 'react';
import {
  AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

export type ReelProps = {
  scenes: {src: string; durationFrames: number}[];
  voiceAudio: string;
  sloganAudio: string;
  logo: string;
  subtitles: {text: string; startFrame: number; endFrame: number}[];
  voiceFrames: number;
  totalFrames: number;
  fps: number;
};

const SceneImage: React.FC<{src: string; durationFrames: number; index: number}> = ({src, durationFrames, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fade = Math.min(14, Math.floor(fps * 0.45));
  const opacity = interpolate(frame, [0, fade, Math.max(fade + 1, durationFrames - fade), durationFrames], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const zoom = interpolate(frame, [0, Math.max(1, durationFrames)], [1.035, 1.13]);
  const drift = interpolate(frame, [0, Math.max(1, durationFrames)], [index % 2 ? 22 : -22, index % 2 ? -18 : 18]);
  return (
    <AbsoluteFill style={{opacity, overflow: 'hidden', backgroundColor: '#071321'}}>
      <Img src={staticFile(src)} style={{
        width: '100%', height: '100%', objectFit: 'cover',
        transform: `scale(${zoom}) translate3d(${drift}px, ${index % 2 ? -10 : 10}px, 0)`,
      }}/>
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(3,12,24,.06) 0%, rgba(3,12,24,.08) 55%, rgba(3,12,24,.58) 100%)'}}/>
      <div style={{position:'absolute',top:72,left:64,width:72,height:5,background:'#C8A45D',borderRadius:8,opacity:.95}}/>
    </AbsoluteFill>
  );
};

const Subtitle: React.FC<{text:string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config:{damping:18,stiffness:180}});
  const y = interpolate(enter,[0,1],[24,0]);
  return (
    <div style={{position:'absolute',left:64,right:64,bottom:245,display:'flex',justifyContent:'center',transform:`translateY(${y}px)`,opacity:enter}}>
      <div dir="rtl" style={{
        maxWidth:930,padding:'22px 30px',borderRadius:22,
        background:'rgba(5,17,31,.82)',border:'1px solid rgba(210,177,111,.72)',
        color:'#FFFDF7',fontFamily:'Noto Sans Arabic, Arial, sans-serif',
        fontSize:48,fontWeight:800,lineHeight:1.48,textAlign:'center',
        textShadow:'0 2px 12px rgba(0,0,0,.28)',
      }}>{text}</div>
    </div>
  );
};

export const KhyratLegalReel: React.FC<ReelProps> = (props) => {
  const {fps} = useVideoConfig();
  const overlap = Math.round(fps * .45);
  const base = Math.floor(props.voiceFrames / Math.max(1, props.scenes.length));
  return (
    <AbsoluteFill style={{backgroundColor:'#071321'}}>
      {props.scenes.map((scene,index) => {
        const from = Math.max(0,index * base - (index ? overlap : 0));
        const duration = Math.min(props.voiceFrames - from, scene.durationFrames || base + overlap);
        return <Sequence key={scene.src} from={from} durationInFrames={Math.max(1,duration)}>
          <SceneImage src={scene.src} durationFrames={Math.max(1,duration)} index={index}/>
        </Sequence>;
      })}
      <Sequence from={0} durationInFrames={props.voiceFrames}>
        <Audio src={staticFile(props.voiceAudio)} volume={1}/>
      </Sequence>
      {props.subtitles.map((line,index) => (
        <Sequence key={index} from={line.startFrame} durationInFrames={Math.max(1,line.endFrame-line.startFrame)}>
          <Subtitle text={line.text}/>
        </Sequence>
      ))}
      <Sequence from={props.voiceFrames} durationInFrames={Math.max(1,props.totalFrames-props.voiceFrames)}>
        <AbsoluteFill style={{background:'linear-gradient(145deg,#071321 0%,#10243A 58%,#071321 100%)',justifyContent:'center',alignItems:'center'}}>
          <div style={{position:'absolute',width:820,height:820,border:'2px solid rgba(201,164,93,.38)',borderRadius:410}}/>
          <div style={{position:'absolute',width:650,height:650,border:'1px solid rgba(201,164,93,.25)',borderRadius:325}}/>
          <Img src={staticFile(props.logo)} style={{width:520,maxHeight:520,objectFit:'contain'}}/>
          <div dir="rtl" style={{marginTop:46,color:'#F5EBDD',fontFamily:'Noto Sans Arabic,Arial,sans-serif',fontSize:54,fontWeight:800}}>خليك فاكر دايمًا</div>
          <div dir="rtl" style={{marginTop:18,color:'#D3B16E',fontFamily:'Noto Sans Arabic,Arial,sans-serif',fontSize:70,fontWeight:900}}>اسأل محمود</div>
          <div style={{position:'absolute',bottom:110,width:110,height:5,background:'#C8A45D',borderRadius:5}}/>
        </AbsoluteFill>
        <Audio src={staticFile(props.sloganAudio)} volume={1}/>
      </Sequence>
    </AbsoluteFill>
  );
};
