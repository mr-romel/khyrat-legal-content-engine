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

const GOLD = '#D6B36D';
const INK = '#06111F';

const SceneImage: React.FC<{src: string; durationFrames: number; index: number}> = ({src, durationFrames, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const edge = Math.min(18, Math.floor(fps * .6));
  const opacity = interpolate(frame, [0, edge, Math.max(edge + 1, durationFrames - edge), durationFrames], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const progress = interpolate(frame, [0, Math.max(1, durationFrames)], [0, 1], {extrapolateRight: 'clamp'});
  const zoom = interpolate(progress, [0, 1], [1.04, 1.19]);
  const direction = index % 2 === 0 ? 1 : -1;
  const driftX = interpolate(progress, [0, 1], [-26 * direction, 26 * direction]);
  const driftY = interpolate(progress, [0, 1], [18, -18]);
  const reveal = spring({frame, fps, config: {damping: 22, stiffness: 105}});
  const wipe = interpolate(frame, [0, edge * 1.25], [100, 0], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{opacity, overflow: 'hidden', backgroundColor: INK}}>
      <Img src={staticFile(src)} style={{
        width: '100%', height: '100%', objectFit: 'cover',
        transform: `scale(${zoom}) translate3d(${driftX}px, ${driftY}px, 0)`,
        filter: 'saturate(1.08) contrast(1.04)',
      }}/>
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(3,12,24,.04) 0%, rgba(3,12,24,.08) 48%, rgba(3,12,24,.76) 100%)'}}/>
      <AbsoluteFill style={{background: 'linear-gradient(110deg, rgba(4,13,25,.32), transparent 55%, rgba(201,164,93,.10))'}}/>
      <div style={{position:'absolute',top:74,left:64,right:64,display:'flex',alignItems:'center',gap:16,opacity:reveal}}>
        <div style={{width:58,height:5,background:GOLD,borderRadius:8}}/>
        <div style={{color:'#FFF4DE',fontFamily:'Arial,sans-serif',fontSize:23,fontWeight:800,letterSpacing:3}}>ASK MAHMOUD</div>
        <div style={{marginLeft:'auto',border:'1px solid rgba(214,179,109,.7)',borderRadius:30,padding:'10px 17px',color:'#F7E9C9',fontSize:20,fontWeight:800,background:'rgba(4,14,27,.42)'}}>LEGAL INSIGHT</div>
      </div>
      <div style={{position:'absolute',left:64,right:64,bottom:178,height:5,background:'rgba(255,255,255,.22)',borderRadius:8,overflow:'hidden'}}>
        <div style={{height:'100%',width:`${Math.max(0,Math.min(100,progress*100))}%`,background:GOLD,borderRadius:8}}/>
      </div>
      <div style={{position:'absolute',top:'42%',left:-180,width:420,height:420,border:'2px solid rgba(214,179,109,.26)',borderRadius:420,transform:`translateX(${wipe}px) scale(${.8 + reveal*.2})`}}/>
      <div style={{position:'absolute',top:'44%',right:-110,width:250,height:250,border:'1px solid rgba(255,255,255,.18)',borderRadius:250}}/>
    </AbsoluteFill>
  );
};

const MotionGraphics: React.FC<{index:number; durationFrames:number}> = ({index,durationFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = interpolate(frame,[0,Math.max(1,durationFrames)],[0,1],{extrapolateRight:'clamp'});
  const sweep = interpolate(frame,[0,Math.round(fps*.9)],[ -260, 1420 ],{extrapolateRight:'clamp'});
  const pulse = .45 + .25*Math.sin(frame/9);
  const enter = spring({frame,fps,config:{damping:19,stiffness:120}});
  return (
    <AbsoluteFill style={{pointerEvents:'none'}}>
      <div style={{position:'absolute',left:54,top:160,width:5,height:190,background:'linear-gradient(180deg,transparent,rgba(214,179,109,.95),transparent)',transform:`scaleY(${enter})`,transformOrigin:'top'}}/>
      <div style={{position:'absolute',right:62,top:172,color:'rgba(255,246,225,.88)',fontFamily:'Arial,sans-serif',fontSize:19,fontWeight:800,letterSpacing:4,textAlign:'right'}}>
        <div style={{color:GOLD,fontSize:17,letterSpacing:5}}>KHYRAT / LEGAL</div>
        <div style={{fontSize:35,marginTop:8,fontVariantNumeric:'tabular-nums'}}>{String(index+1).padStart(2,'0')}<span style={{color:GOLD,opacity:.8}}> / 05</span></div>
      </div>
      <div style={{position:'absolute',left:58,right:58,top:390,height:1,background:'linear-gradient(90deg,rgba(214,179,109,0),rgba(214,179,109,.45),rgba(214,179,109,0))',opacity:pulse}}/>
      <svg viewBox="0 0 1080 1920" style={{position:'absolute',inset:0,width:'100%',height:'100%'}}>
        <defs>
          <linearGradient id={`sweep-${index}`} x1="0" x2="1">
            <stop offset="0" stopColor="#D6B36D" stopOpacity="0"/>
            <stop offset=".5" stopColor="#FFF1C9" stopOpacity=".55"/>
            <stop offset="1" stopColor="#D6B36D" stopOpacity="0"/>
          </linearGradient>
        </defs>
        <path d="M54 500 V430 Q54 410 74 410 H180" fill="none" stroke="#D6B36D" strokeOpacity=".65" strokeWidth="2"/>
        <path d="M1026 500 V430 Q1026 410 1006 410 H900" fill="none" stroke="#D6B36D" strokeOpacity=".65" strokeWidth="2"/>
        <circle cx="880" cy="1050" r={220 + 18*Math.sin(frame/16)} fill="none" stroke="#D6B36D" strokeOpacity={pulse*.55} strokeWidth="2" strokeDasharray="4 18"/>
        <circle cx="880" cy="1050" r="172" fill="none" stroke="#FFFFFF" strokeOpacity=".18" strokeWidth="1"/>
        <path d={`M${sweep} 420 L${sweep+150} 420 L${sweep-40} 1510 L${sweep-190} 1510 Z`} fill={`url(#sweep-${index})`} opacity=".23"/>
      </svg>
      <div style={{position:'absolute',left:64,bottom:208,color:'rgba(255,244,220,.7)',fontSize:16,fontWeight:800,letterSpacing:3}}>YOUR RIGHTS • YOUR AWARENESS</div>
    </AbsoluteFill>
  );
};

const Subtitle: React.FC<{text:string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config:{damping:16,stiffness:165,mass:.75}});
  const y = interpolate(enter,[0,1],[42,0]);
  const scale = interpolate(enter,[0,1],[.96,1]);
  return (
    <div style={{position:'absolute',left:54,right:54,bottom:260,display:'flex',justifyContent:'center',transform:`translateY(${y}px) scale(${scale})`,opacity:enter}}>
      <div dir="rtl" style={{
        maxWidth:950,padding:'24px 32px',borderRadius:24,
        background:'linear-gradient(135deg,rgba(5,17,31,.94),rgba(12,32,51,.88))',
        border:'1px solid rgba(214,179,109,.9)',boxShadow:'0 18px 60px rgba(0,0,0,.38)',
        color:'#FFFDF7',fontFamily:'Noto Sans Arabic, Arial, sans-serif',
        fontSize:49,fontWeight:900,lineHeight:1.5,textAlign:'center',
        textShadow:'0 3px 14px rgba(0,0,0,.42)',
      }}>{text}</div>
    </div>
  );
};

const SceneTransition: React.FC<{index:number}> = ({index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.round(fps * .62);
  const opacity = interpolate(frame,[0, duration*.28, duration],[0,.82,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
  const scale = interpolate(frame,[0,duration],[.72,1.42],{extrapolateRight:'clamp'});
  return <AbsoluteFill style={{opacity,background:'linear-gradient(115deg,rgba(4,13,25,.98),rgba(214,179,109,.82),rgba(255,245,220,.26),rgba(4,13,25,.98))',transform:`scaleX(${scale})`,transformOrigin:index%2?'right center':'left center'}}/>;
};

const BrandEndCard: React.FC<{logo:string}> = ({logo}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = spring({frame,fps,config:{damping:18,stiffness:95}});
  const glow = interpolate(Math.sin(frame/13),[-1,1],[.25,.62]);
  return (
    <AbsoluteFill style={{background:'radial-gradient(ellipse at 50% 42%,#18314B 0%,#091827 54%,#030A12 100%)',justifyContent:'center',alignItems:'center',overflow:'hidden'}}>
      <div style={{position:'absolute',width:1180,height:1180,border:'2px solid rgba(214,179,109,.28)',borderRadius:600,opacity:glow,transform:`scale(${.92+entrance*.08})`}}/>
      <div style={{position:'absolute',width:940,height:940,border:'1px solid rgba(214,179,109,.22)',borderRadius:500,opacity:.8}}/>
      <div style={{position:'absolute',width:720,height:720,border:'1px solid rgba(255,255,255,.10)',borderRadius:400}}/>
      <Img src={staticFile(logo)} style={{
        position:'absolute',width:'100%',height:'100%',maxWidth:1080,maxHeight:1920,
        objectFit:'contain',padding:34,boxSizing:'border-box',
        transform:`scale(${interpolate(entrance,[0,1],[.88,1])})`,
        filter:'drop-shadow(0 18px 38px rgba(0,0,0,.48))',
      }}/>
      <div style={{position:'absolute',bottom:92,width:140,height:5,borderRadius:8,background:GOLD,opacity:entrance}}/>
    </AbsoluteFill>
  );
};

export const KhyratLegalReel: React.FC<ReelProps> = (props) => {
  const {fps} = useVideoConfig();
  const overlap = Math.round(fps * .48);
  const base = Math.floor(props.voiceFrames / Math.max(1, props.scenes.length));
  return (
    <AbsoluteFill style={{backgroundColor:INK}}>
      {props.scenes.map((scene,index) => {
        const from = Math.max(0,index * base - (index ? overlap : 0));
        const duration = Math.min(props.voiceFrames - from, scene.durationFrames || base + overlap);
        return <Sequence key={scene.src} from={from} durationInFrames={Math.max(1,duration)}>
          <SceneImage src={scene.src} durationFrames={Math.max(1,duration)} index={index}/><MotionGraphics index={index} durationFrames={Math.max(1,duration)}/>
        </Sequence>;
      })}
      {props.scenes.slice(1).map((scene,index) => {
        const from = Math.max(0,(index+1)*base-overlap);
        return <Sequence key={`transition-${scene.src}`} from={from} durationInFrames={overlap}>
          <SceneTransition index={index}/>
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
        <BrandEndCard logo={props.logo}/>
        <Audio src={staticFile(props.sloganAudio)} volume={1}/>
      </Sequence>
    </AbsoluteFill>
  );
};
