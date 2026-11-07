import { memo, useId, useMemo, useState } from 'react';
import type { Frame } from './types';
import { teamColor } from './types';

export function columnLabel(index:number):string {let result='';for(let n=index+1;n>0;n=Math.floor((n-1)/26))result=String.fromCharCode(65+(n-1)%26)+result;return result;}

function Board({frame,history,speed=1}: {frame: Frame | null;history?:Frame[];speed?:number;playing?:boolean}) {
  const [selected, setSelected] = useState('all');
  const [cellSize,setCellSize] = useState(16);
  const [hovered,setHovered] = useState<number[]|null>(null);
  const [picked,setPicked] = useState<number[]|null>(null);
  const id = useId().replaceAll(':','');
  const clipId = `seaClip${id}`, gridId=`grid${id}`;
  // Pre-v1.5 recordings had no config and always used a 40-cell sea.
  const map=frame?.config?.map??(frame?{rows:40,cols:40}:{rows:36,cols:36});
  const {rows,cols}=map;
  const coordinate = hovered ?? picked;
  function pointerCell(event: React.MouseEvent<SVGRectElement>) {const bounds=event.currentTarget.getBoundingClientRect();return [Math.max(0,Math.min(rows-1,Math.floor((event.clientY-bounds.top)/bounds.height*rows))),Math.max(0,Math.min(cols-1,Math.floor((event.clientX-bounds.left)/bounds.width*cols)))];}
  const traces = frame?.traces.filter(t => selected === 'all' || t.seat === selected) ?? [];
  const arc = traces[0];
  const maxHeight = Math.max(1, ...(arc?.points.map(p => p[2]) ?? []));
  const shotCells=useMemo(()=>{
  const shotCells=new Map<string,{r:number;c:number;points:number;details:string[]}>();
  for(const recorded of history??(frame?[frame]:[])) {
    if(frame&&recorded.tick>frame.tick)break;
    const targets=new Map<string, {cells:number[][]}>();
    for(const team of recorded.teams) for(const ship of team.ships) for(const [r,c] of ship.cells) targets.set(`${r}-${c}`,ship);
    for(const team of recorded.teams) {
      if(selected!=='all'&&team.seat!==selected)continue;
      const torpedo=recorded.traces.some(trace=>trace.seat===team.seat&&trace.kind==='torpedo');
      const firstScoringShot=team.shots.findIndex(shot=>shot[2]==='hit'||shot[2]==='sunk');
      team.shots.forEach(([row,col,result],index)=>{
        if(result==='flare')return;
        const r=Number(row),c=Number(col);
        const target=targets.get(`${r}-${c}`);
        const points=recorded.events?.find(e=>e.seat===team.seat)?.result_points?.[index]??(result==='hit'?1:result==='sunk'?1+(!torpedo||index===firstScoringShot?(target?.cells.length??0):0):0);
        const key=`${r}-${c}`;
        const cell=shotCells.get(key)??{r,c,points:0,details:[]};
        cell.points+=points;
        if(cell.details.length<8)cell.details.push(`${team.seat}: ${String(result)} (${points} points), tick ${recorded.tick}`);
        shotCells.set(key,cell);
      });
    }
  }
  return shotCells;
  },[frame,history,selected]);
  const scene=useMemo(()=>(<g clipPath={`url(#${clipId})`}>{frame?.teams.map(team => <g key={team.seat}>
        {team.ships.flatMap(ship => ship.cells.map(([r,c]) => {
          const holed = ship.holes.some(([hr,hc]) => hr === r && hc === c);
          return <g key={`${ship.name}-${r}-${c}`}><rect x={c+.1} y={r+.1} width=".8" height=".8" rx=".15" fill={teamColor(team.seat)} opacity={ship.sunk ? .25 : holed ? .45 : .9}><title>{team.seat} · {ship.name} [{r}, {c}] {holed ? 'hit' : 'afloat'}</title></rect>{holed && <path d={`M${c+.2} ${r+.2}l.6 .6m0-.6l-.6 .6`} stroke="#fff" strokeWidth=".08"/>}</g>;
        }))}
      </g>)}
      {[...shotCells].map(([key,{r,c,points,details}])=><g key={key}>
        <title>{details.join('\n')}</title>
        <rect x={c+.08} y={r+.08} width=".84" height=".84" fill="#102832" fillOpacity=".8" stroke={points>0?'#63e6be':'#c8e2ec'} strokeWidth=".055"/>
        <text x={c+.5} y={r+.71} textAnchor="middle" fontSize=".65" fontWeight="bold" fill={points>0?'#63e6be':'#c8e2ec'} pointerEvents="none">{points}</text>
      </g>)}
      {traces.map((trace, i) => <g key={`${frame?.tick}-${i}`} className={`trajectory trajectory-${trace.kind}`}><polyline points={trace.points.map(p => `${p[1]+.5},${p[0]+.5}`).join(' ')} fill="none" stroke={trace.kind==='cluster'||trace.kind==='torpedo'?'#ff3b30':teamColor(trace.seat)} strokeWidth={trace.kind==='torpedo'?'.2':'.09'} strokeDasharray=".3 .2"/><circle className="impact-ring" cx={trace.landing[1]+.5} cy={trace.landing[0]+.5} r=".38" fill="none" stroke={trace.kind==='cluster'||trace.kind==='torpedo'?'#ff3b30':teamColor(trace.seat)} strokeWidth=".1"/></g>)}
      {traces.map((trace,i)=><circle key={`projectile-${frame?.tick}-${i}`} className="projectile" r={trace.kind==='torpedo'?'.18':'.12'} fill={trace.kind==='cluster'||trace.kind==='torpedo'?'#ff3b30':trace.kind==='flare'?'#ffe066':teamColor(trace.seat)}><animateMotion dur={`${Math.min(1000,300/speed)*.65}ms`} fill="freeze" path={trace.points.map((p,j)=>`${j?'L':'M'}${p[1]+.5},${p[0]+.5}`).join(' ')}/></circle>)}
      <g key={frame?.tick} className="battle-effects" pointerEvents="none">
        {frame?.events?.filter(e=>selected==='all'||e.seat===selected).map((event,i)=><g key={i} className={`effect-${event.kind}`} aria-label={`${event.seat} ${event.kind} activation`}>
          <circle className="activation-ring" cx={event.origin[1]+.5} cy={event.origin[0]+.5} r=".6" fill="none" stroke={teamColor(event.seat)} strokeWidth=".12"/>
          {event.kind==='flare'&&event.results[0]&&<rect className="flare-zone" x={Number(event.results[0][1])-3} y={Number(event.results[0][0])-3} width="7" height="7" fill="#ffe066" fillOpacity=".18" stroke="#ffe066" strokeWidth=".1"/>}
          {event.kind==='teleport'&&[...event.from_cells,...event.cells].map(([r,c],j)=><rect key={j} className="teleport-cell" x={c+.05} y={r+.05} width=".9" height=".9" rx=".2" fill="#da77f2" fillOpacity=".35" stroke="#da77f2" strokeWidth=".12"/>)}
          {event.sunk_cells?.map(([r,c],j)=><rect key={`sunk-${j}`} className="sinking-cell" x={c} y={r} width="1" height="1" fill="#ff6b6b" fillOpacity=".2" stroke="#ff6b6b" strokeWidth=".15"/>)}
          {event.results.filter(s=>s[2]!=='flare').map(([r,c,result],j)=><circle key={j} className={`effect-impact impact-${result}`} cx={Number(c)+.5} cy={Number(r)+.5} r={result==='sunk'?'.65':'.4'} fill={result==='hit'||result==='sunk'?'#ff922b':'#74c0fc'} fillOpacity=".55" stroke={event.kind==='cluster'||event.kind==='torpedo'?'#ff3b30':'#fff'} strokeWidth=".08"><title>{event.seat} {event.kind}: {String(result)}</title></circle>)}
        </g>)}
  </g></g>),[frame,selected,shotCells,speed,clipId]);
  return <div className="board-panel" style={{'--effect-duration':`${Math.min(1000,300/speed)}ms`} as React.CSSProperties}>
    <div className="panel-heading"><div><span className="eyebrow">LIVE SEA / {rows} × {cols}</span><h2>Battle field</h2></div>
      <label>Trajectories<select aria-label="Trajectory team" value={selected} onChange={e => setSelected(e.target.value)}><option value="all">All teams</option>{frame?.teams.map(t => <option key={t.seat}>{t.seat}</option>)}</select></label></div>
    <div className="grid-tools"><label>Zoom<input aria-label="Grid zoom" type="range" min="12" max="36" value={cellSize} onChange={e=>setCellSize(Number(e.target.value))}/></label><output aria-live="polite">{coordinate?`${columnLabel(coordinate[1])}${coordinate[0]+1} · [row ${coordinate[0]}, col ${coordinate[1]}]`:'Hover or click a cell'}</output></div>
    <div className="grid-scroll" style={{'--cell-size':`${cellSize}px`,'--board-cols':cols} as React.CSSProperties}><div className="grid-sheet"><div className="grid-header"><span className="grid-corner">↘</span><div className="column-labels">{Array.from({length:cols},(_,c)=><span key={c}>{columnLabel(c)}</span>)}</div></div><div className="grid-body"><div className="row-labels">{Array.from({length:rows},(_,r)=><span key={r}>{r+1}</span>)}</div>
    <svg viewBox={`0 0 ${cols} ${rows}`} role="img" aria-label={`${rows} by ${cols} battle board`} className="sea" style={{width:cellSize*cols,height:cellSize*rows,maxHeight:'none',margin:0,flexShrink:0}}>
      <defs><pattern id={gridId} width="1" height="1" patternUnits="userSpaceOnUse"><path d="M 1 0 L 0 0 0 1" fill="none" stroke="#284756" strokeWidth=".035"/></pattern><clipPath id={clipId}><rect width={cols} height={rows}/></clipPath></defs>
      <rect width={cols} height={rows} fill="#102832"/><rect width={cols} height={rows} fill={`url(#${gridId})`}/>
      {scene}
      {picked&&<rect x={picked[1]+.04} y={picked[0]+.04} width=".92" height=".92" fill="none" stroke="#fff" strokeWidth=".08"/>}
      <rect width={cols} height={rows} fill="transparent" role="button" aria-label="Battle grid coordinate picker" tabIndex={0} onMouseMove={e=>{const cell=pointerCell(e);setHovered(old=>old?.[0]===cell[0]&&old?.[1]===cell[1]?old:cell);}} onMouseLeave={()=>setHovered(null)} onClick={e=>setPicked(pointerCell(e))} onKeyDown={e=>{const [r,c]=picked??[0,0];const moves:Record<string,number[]>={ArrowUp:[r-1,c],ArrowDown:[r+1,c],ArrowLeft:[r,c-1],ArrowRight:[r,c+1],Enter:[r,c],' ':[r,c]};if(moves[e.key]){e.preventDefault();setPicked(moves[e.key].map((n,i)=>Math.max(0,Math.min((i===0?rows:cols)-1,n))));}}}><title>{coordinate?`${columnLabel(coordinate[1])}${coordinate[0]+1} · row ${coordinate[0]}, col ${coordinate[1]}`:'Hover or click a cell; arrow keys select coordinates'}</title></rect>
    </svg></div></div></div>
    <div className="sea-footer"><span>Top-down paths · dashed lines show latest tick</span><span className="wind-indicator"><svg width="40" height="40" viewBox="0 0 40 40" role="img" aria-label="Wind direction and strength"><defs><marker id="wind-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0L5 2.5L0 5" fill="#63e6be"/></marker></defs><circle cx="20" cy="20" r="18" fill="none" stroke="#3a535e"/><path d="M20 2V6M20 34V38M2 20H6M34 20H38" stroke="#7ea7b2"/><line x1="20" y1="20" x2={20+(frame?.wind[1] ?? 0)*15} y2={20+(frame?.wind[0] ?? 0)*15} stroke="#63e6be" strokeWidth="1.5" markerEnd="url(#wind-arrow)"/></svg><span>Wind <b>{frame?.wind.map(n => n.toFixed(2)).join(', ') ?? '—'}</b><small>(row, col) · constant</small></span></span></div>
    {arc && <div className="arc"><div><span className="eyebrow">FLIGHT PROFILE · TEAM {arc.seat}</span><p>{arc.kind} / {arc.result} · {arc.flight_seconds.toFixed(2)} s</p></div><svg viewBox="0 0 240 60" role="img" aria-label="Shot height over flight time"><path d="M0 55H240" stroke="#466371"/><polyline points={arc.points.map((p,i) => `${i/(arc.points.length-1)*240},${55-p[2]/maxHeight*45}`).join(' ')} fill="none" stroke={teamColor(arc.seat)} strokeWidth="2"/></svg></div>}
  </div>;
}
export default memo(Board);
