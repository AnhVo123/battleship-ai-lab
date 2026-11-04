export const COSTS:Record<string,number> = {flare:4,cluster:1,torpedo:7,teleport:4};
export function unlocked(round:string) {return round==='round1'?[]:round==='round2'?['flare','cluster']:round==='final'?Object.keys(COSTS):[];}
export default function Armory({round,loadout,onChange,carryover,advanced,onAdvanced,sources=[],onSource}:{round:string;loadout:Record<string,number>;onChange:(value:Record<string,number>)=>void;carryover:{id:string;points:number}|null;advanced:boolean;onAdvanced:(value:boolean)=>void;sources?:{id:string;points:number;label:string}[];onSource?:(id:string)=>void}) {
  const available = unlocked(round);
  const budget = (round==='round1'?0:10)+(round==='final'&&advanced&&carryover?carryover.points:0);
  const spent = Object.entries(loadout).reduce((sum,[name,count])=>sum+(COSTS[name]??0)*count,0);
  return <div className="armory"><span className="eyebrow">PRE-BATTLE ARMORY</span>{round==='all'?<p className="fine">All-round benchmarks use an empty loadout; Round 1 sells nothing.</p>:available.length===0?<p className="fine">Round 1 has no boosters or purchase points.</p>:available.map(name=><label className="armory-row" key={name}><span>{name[0].toUpperCase()+name.slice(1)} <small>{COSTS[name]} points each</small></span><input aria-label={`${name} quantity`} type="number" min="0" max={Math.floor(budget/COSTS[name])} step="1" value={loadout[name]??0} onChange={e=>{const count=Number(e.target.value);if(Number.isInteger(count)&&count>=0)onChange({...loadout,[name]:count});}}/></label>)}
    {round==='final'&&sources.length>0&&<label>Round 2 carryover source<select value={carryover?.id??''} onChange={e=>onSource?.(e.target.value)}><option value="">No carryover</option>{sources.map(s=><option key={s.id} value={s.id}>{s.label} · {s.points} points</option>)}</select></label>}
    {round==='final'&&carryover&&<label className="check-label"><input type="checkbox" checked={advanced} onChange={e=>onAdvanced(e.target.checked)}/>Team A advanced from completed Round 2 (+{carryover.points} unspent points)</label>}
    <p className={spent>budget?'error':'fine'} role="status">Budget {budget} · Spent {spent} · Remaining {budget-spent}</p><p className="fine">Purchases apply before the battle. Used inventory is spent; unused boosters expire with no refund. Only unspent points carry after declared advancement.</p>
  </div>;
}
