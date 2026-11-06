import { memo, useEffect, useRef, useState } from 'react';
import Board from './Board';
import ReplayTimeline from './ReplayTimeline';
import { BoosterDetails } from './BattleResults';
import type { Frame } from './types';

type Finding = {id?:string; tick?:number; classification:string; code:string; message:string; evidence: Record<string,unknown>[]};
type Diagnostic = {findings:Finding[]; metrics?:Record<string,unknown>; boosters?:Record<string,unknown>; events?:Record<string,unknown>[]; limits?:string[]};
type RecordData = {seed:number; diagnostics?:Diagnostic; replay?:{deltas:unknown[]}};
type Experiment = {id:string;kind:string;title:string;created_at:string;diagnostics:Diagnostic;frames?:Frame[];
  report?:{pool:string;rounds:Record<string,{strategies:{version:string;records:RecordData[]}[]}>}};
type History = Pick<Experiment,'id'|'kind'|'title'|'created_at'>;

async function request<T>(path:string, body?:unknown):Promise<T> {
  const response = await fetch(`/api${path}`,{...(body !== undefined ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {})});
  if(!response.ok) {const value = await response.json();throw new Error(typeof value.detail==='string' ? value.detail : JSON.stringify(value.detail));}
  return response.json() as Promise<T>;
}

export function Findings({diagnostic,onJump}:{diagnostic:Diagnostic;onJump?:(tick:number)=>void}) {
  const [filter,setFilter] = useState('all');
  const findings = diagnostic.findings.filter(f => filter==='all' || f.classification===filter);
  return <><label>Evidence classification<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All findings</option>{['confirmed_error','confirmed_observation','hypothesis','hindsight'].map(c=><option key={c}>{c}</option>)}</select></label>
    <p className="fine">Confirmed errors are recorded runtime/validation failures or friendly damage. Observations report outcomes. Hypotheses require testing. Hindsight uses information hidden from the bot.</p>
    <div className="issue-list">{findings.slice(0,200).map((f,i)=><article className={`issue ${f.classification}`} key={f.id ?? i}><div className="issue-heading"><span className="badge">{f.classification.replaceAll('_',' ')}</span>{f.tick !== undefined && onJump && <button onClick={()=>onJump(f.tick!)}>Jump to tick {f.tick}</button>}</div><h4>{f.code.replaceAll('_',' ')}</h4><p>{f.message}</p><details><summary>Simulation evidence</summary><pre>{JSON.stringify(f.evidence,null,2)}</pre>{diagnostic.events?.filter(e=>f.evidence.some(ref=>ref.event===e.id)).map((e,j)=><pre key={j}>{JSON.stringify(e,null,2)}</pre>)}</details></article>)}</div>
    {findings.length===0 && <p className="empty">No findings in this category. This does not establish that the strategy is optimal.</p>}
    {findings.length>200 && <p className="fine">Showing 200 markers. The exported evidence contains the full findings.</p>}</>;
}

function FailurePanelView({battle,tick,onJump,onSaved}:{battle:string;tick:number;onJump:(tick:number)=>void;onSaved?:()=>void}) {
  const [diagnostic,setDiagnostic]=useState<Diagnostic|null>(null);
  const [error,setError]=useState('');
  const [saved,setSaved]=useState('');
  useEffect(()=>{let active=true;request<Diagnostic>(`/battles/${battle}/diagnostics`).then(d=>{if(active)setDiagnostic(d);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[battle,tick]);
  return <section className="panel"><span className="eyebrow">FAILURE REPLAY · RECORDED EVIDENCE</span><h2>Strategy diagnostics</h2>{error && <p role="alert">{error}</p>}{diagnostic && <><Metrics diagnostic={diagnostic}/><Findings diagnostic={diagnostic} onJump={onJump}/></>}<button onClick={()=>{request<Experiment>(`/battles/${battle}/experiments`,{}).then(e=>{setSaved(e.id);onSaved?.();}).catch(e=>setError(String(e)));}}>Save experiment snapshot</button>{saved && <p className="fine">Saved experiment {saved.slice(0,12)}. Open Diagnostics & history to export or generate a prompt.</p>}</section>;
}

export const FailurePanel=memo(FailurePanelView);

function Metrics({diagnostic}:{diagnostic:Diagnostic}) {
  const metrics = diagnostic.metrics ?? {};
  return <><div className="diagnostic-metrics">{[
    ['Recorded points',metrics.points],['Cell-hit points',metrics.enemy_cell_points],['Sink-bonus points',metrics.sink_bonus_points],['Wasted results',metrics.wasted_results],['Enemy hit-result rate',metrics.enemy_hit_result_rate],
    ['Wind displacement (cells)',metrics.mean_wind_displacement_cells],
    ['Declared target error (cells)',metrics.mean_declared_target_error_cells],
    ['Reported wind error (hindsight)',metrics.mean_reported_wind_error]
  ].map(([name,value])=><div key={String(name)}><small>{String(name)}</small><b>{typeof value==='number'?value.toFixed(2):'Unavailable'}</b></div>)}</div><p className="fine">Target samples: {String(metrics.target_samples ?? 0)} · wind-estimate samples: {String(metrics.reported_wind_samples ?? 0)}. Missing self-reported metadata is not a strategy error.</p>
  {Object.keys(diagnostic.boosters ?? {}).length>0 && <details><summary>Booster effectiveness: observed rewards, waste and reveals</summary><pre>{JSON.stringify(diagnostic.boosters,null,2)}</pre><p className="fine">These are observed action rewards; they do not measure counterfactual benefit. Flare information and teleport survival value are not inferred.</p></details>}</>;
}

export default function Diagnostics({battle}:{battle:string}) {
  const [history,setHistory]=useState<History[]>([]);
  const [experiment,setExperiment]=useState<Experiment|null>(null);
  const [error,setError]=useState('');
  const [prompt,setPrompt]=useState('');
  const [copied,setCopied]=useState(false);
  const [development,setDevelopment]=useState('');
  const [validation,setValidation]=useState('');
  const [round,setRound]=useState('');
  const [strategy,setStrategy]=useState(0);
  const [match,setMatch]=useState(0);
  const [replay,setReplay]=useState<Frame|null>(null);
  const [replayTick,setReplayTick]=useState(0);
  const [replayPlaying,setReplayPlaying]=useState(false);
  const [replaySpeed,setReplaySpeed]=useState(1);
  const [replayLoading,setReplayLoading]=useState(false);
  const replaySerial=useRef(0);
  function resetReplay(){replaySerial.current++;setReplay(null);setReplayTick(0);setReplayPlaying(false);setReplayLoading(false);}
  async function refresh() {setHistory(await request<History[]>('/experiments'));}
  useEffect(()=>{refresh().catch(e=>setError(String(e)));},[]);
  async function select(id:string) {setError('');setPrompt('');resetReplay();setStrategy(0);setMatch(0);try{const value=await request<Experiment>(`/experiments/${id}`);setExperiment(value);setRound(Object.keys(value.report?.rounds ?? {})[0] ?? '');}catch(e){setError(String(e));}}
  const run = experiment?.report?.rounds[round]?.strategies[strategy];
  const record = run?.records[match];
  const diagnostic = record?.diagnostics ?? experiment?.diagnostics;
  const maxTick = experiment?.kind==='battle' ? (experiment.frames?.length ?? 1)-1 : record?.replay?.deltas.length ?? 0;
  async function jump(tick:number) {if(!experiment)return;const serial=++replaySerial.current;setReplayLoading(true);try{const frame=await request<Frame>(`/experiments/${experiment.id}/replay/${tick}?round=${encodeURIComponent(round)}&strategy=${strategy}&match=${match}`);if(serial===replaySerial.current){setReplay(frame);setReplayTick(tick);}}catch(e){if(serial===replaySerial.current){setError(String(e));setReplayPlaying(false);}}finally{if(serial===replaySerial.current)setReplayLoading(false);}}
  function seekReplay(tick:number){setReplayPlaying(false);void jump(tick);}
  useEffect(()=>{if(!replayPlaying||replayLoading)return;if(replayTick>=maxTick){setReplayPlaying(false);return;}const timer=setTimeout(()=>void jump(replayTick+1),300/replaySpeed);return()=>clearTimeout(timer);},[replayPlaying,replayLoading,replayTick,maxTick,replaySpeed,experiment?.id,round,strategy,match]);
  async function generatePrompt() {if(!experiment)return;try{const response=await fetch(`/api/experiments/${experiment.id}/prompt?round=${encodeURIComponent(round)}&strategy=${strategy}&match=${match}`);if(!response.ok)throw new Error('Prompt could not be generated');setPrompt(await response.text());setCopied(false);}catch(e){setError(String(e));}}
  return <><section className="panel"><span className="eyebrow">REPRODUCIBLE EXPERIMENTS</span><h2>Diagnostics & history</h2><p className="muted">Original simulation evidence, preserved versions, and clearly labeled interpretations. No AI service is called.</p>{error && <p role="alert" className="error">{error}</p>}
  <div className="controls"><button onClick={()=>{refresh().catch(e=>setError(String(e)));}}>Refresh history</button>{battle && <button onClick={()=>{request<Experiment>(`/battles/${battle}/experiments`,{}).then(async e=>{await refresh();await select(e.id);}).catch(e=>setError(String(e)));}}>Save current battle</button>}</div>
  <label>Experiment history<select value={experiment?.id ?? ''} onChange={e=>{if(e.target.value)void select(e.target.value);}}><option value="">Select an experiment</option>{history.map(e=><option key={e.id} value={e.id}>{e.created_at.slice(0,19)} · {e.title}</option>)}</select></label>
  <details><summary>Compare development against validation</summary><p className="fine">Select compatible benchmark experiments with the same versions, rounds, loadout, opponents, team count and master seed. First is development, second is holdout. Differences are independent-pool observations, not proof of overfitting.</p><div className="input-pair"><label>Development experiment<select value={development} onChange={e=>setDevelopment(e.target.value)}><option value="">Select</option>{history.filter(e=>e.kind==='benchmark').map(e=><option key={e.id} value={e.id}>{e.title} · {e.id.slice(0,8)}</option>)}</select></label><label>Validation experiment<select value={validation} onChange={e=>setValidation(e.target.value)}><option value="">Select</option>{history.filter(e=>e.kind==='benchmark').map(e=><option key={e.id} value={e.id}>{e.title} · {e.id.slice(0,8)}</option>)}</select></label></div><button disabled={!development||!validation} onClick={()=>{request<Experiment>('/experiments/compare-pools',{development,validation}).then(async e=>{await refresh();await select(e.id);}).catch(e=>setError(String(e)));}}>Compare pools</button></details></section>
  {experiment && <><section className="panel"><h3>{experiment.title}</h3><p className="fine">{experiment.id} · {experiment.created_at} · Local approximation</p><div className="controls">{['json','csv','markdown'].map(format=><a className="export-link" key={format} href={`/api/experiments/${experiment.id}/export/${format}`}>Export {format.toUpperCase()}</a>)}<button onClick={()=>void generatePrompt()}>Generate improvement prompt</button></div>
  {experiment.kind==='benchmark' && <><h4 className="subheading">A/B regression analysis</h4><p className="fine">First version is baseline; later version is candidate. Flags use exploratory 95% paired intervals without multiple-testing correction.</p><Findings diagnostic={{findings:experiment.diagnostics.findings.filter(f=>['regression','improvement'].includes(f.code))}}/>
  <div className="benchmark-options"><label>Round<select value={round} onChange={e=>{setRound(e.target.value);setStrategy(0);setMatch(0);resetReplay();}}>{Object.keys(experiment.report?.rounds ?? {}).map(name=><option key={name}>{name}</option>)}</select></label><label>Strategy<select value={strategy} onChange={e=>{setStrategy(Number(e.target.value));setMatch(0);resetReplay();}}>{experiment.report?.rounds[round]?.strategies.map((s,i)=><option key={s.version} value={i}>{i===0?'Baseline':'Candidate'} · {s.version.split(/[\\/]/).pop()?.slice(0,12)}</option>)}</select></label><label>Recorded match<select value={match} onChange={e=>{setMatch(Number(e.target.value));resetReplay();}}>{run?.records.map((r,i)=><option key={i} value={i}>{i+1} · seed {String(r.seed)}</option>)}</select></label></div></>}
  {diagnostic && <><Metrics diagnostic={diagnostic}/><Findings diagnostic={diagnostic} onJump={experiment.kind==='pool_comparison'?undefined:seekReplay}/>{diagnostic.limits?.map(limit=><p className="fine" key={limit}>{limit}</p>)}</>}
  {prompt && <><label>Copyable ChatGPT improvement prompt<textarea rows={12} readOnly value={prompt}/></label><button onClick={()=>{navigator.clipboard.writeText(prompt).then(()=>setCopied(true)).catch(()=>setError('Clipboard unavailable. Select and copy the prompt text.'));}}>{copied?'Copied':'Copy prompt'}</button></>}
  {experiment.kind!=='pool_comparison' && maxTick>0 && <><h4 className="subheading">Original Failure Replay</h4><p className="fine">Jump to an issue marker or scrub recorded ticks. This loads the original evidence; it does not rerun the strategy.</p><ReplayTimeline tick={replayTick} maxTick={maxTick} playing={replayPlaying} speed={replaySpeed} disabled={false} canNext={replayTick<maxTick&&!replayLoading} onSeek={seekReplay} onNext={()=>seekReplay(replayTick+1)} onToggle={()=>setReplayPlaying(!replayPlaying)} onSpeed={setReplaySpeed}/>{replay && <><Board frame={replay} history={experiment.frames} speed={replaySpeed}/>{replay.teams.map(team=><div key={team.seat}><b>Team {team.seat}</b><BoosterDetails team={team}/></div>)}</>}</>}
  </section></>}
  {!experiment && <p className="empty">Save a battle snapshot or complete a benchmark to begin an experiment history. No diagnoses are generated without recorded evidence.</p>}</>;
}
