export default function ReplayTimeline({tick,maxTick,playing,speed,disabled,canNext,onSeek,onNext,onToggle,onSpeed}:{
  tick:number;maxTick:number;playing:boolean;speed:number;disabled:boolean;canNext:boolean;
  onSeek:(tick:number)=>void;onNext:()=>void;onToggle:()=>void;onSpeed:(speed:number)=>void;
}) {
  return <section className="replay-timeline" aria-label="Replay controls"><div className="timeline-heading"><label htmlFor="replay-timeline">Replay timeline</label><output>Tick {tick} / {maxTick}</output></div>
    <input id="replay-timeline" aria-label="Replay tick" type="range" min="0" max={maxTick} step="1" value={tick} disabled={disabled} onChange={e=>onSeek(Number(e.target.value))}/>
    <div className="timeline-buttons"><button disabled={disabled||tick===0} onClick={()=>onSeek(0)}>↺ Restart</button><button disabled={disabled||tick===0} onClick={()=>onSeek(tick-1)}>← Previous</button><button disabled={disabled||!canNext&&!playing} onClick={onToggle}>{playing?'Ⅱ Pause':'▶ Play'}</button><button disabled={disabled||!canNext} onClick={onNext}>Next →</button><label>Playback speed<select aria-label="Playback speed" value={speed} onChange={e=>onSpeed(Number(e.target.value))}>{[.25,.5,1,2,4].map(value=><option key={value} value={value}>{value}×</option>)}</select></label></div><p className="fine">Click or drag to any recorded tick. Seeking pauses playback. Next at the live edge resolves one new tick.</p>
  </section>;
}
