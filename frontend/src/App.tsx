import { useCallback, useEffect, useRef, useState } from 'react';
import Board from './Board';
import ReplayTimeline from './ReplayTimeline';
import BattleResults, { BoosterDetails } from './BattleResults';
import StrategyWorkbench, { PythonPreview } from './LazyStrategy';
import Armory, { COSTS, unlocked } from './Armory';
import Diagnostics, { FailurePanel } from './Diagnostics';
import { estimate, teamColor } from './types';
import type { Frame, Job, Version } from './types';

async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`/api${path}`, {method: method ?? (body === undefined ? 'GET' : 'POST'), headers: {'Content-Type':'application/json'}, ...(body !== undefined ? {body: JSON.stringify(body)} : {})});
  if (!response.ok) {const data = await response.json(); throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));}
  return response.json() as Promise<T>;
}

export default function App() {
  const [tab,setTab] = useState('battle');
  const [versions,setVersions] = useState<Version[]>([]);
  const [version,setVersion] = useState('');
  const [comparison,setComparison] = useState('');
  const [round,setRound] = useState('round1');
  const [difficulty,setDifficulty] = useState('medium');
  const [teams,setTeams] = useState(2);
  const [seed,setSeed] = useState(42);
  const [reproducible,setReproducible] = useState(false);
  const [loadout,setLoadout] = useState<Record<string,number>>({});
  const [carryover,setCarryover] = useState<{id:string;points:number}|null>(null);
  const [advanced,setAdvanced] = useState(false);
  const [carrySources,setCarrySources] = useState<{id:string;points:number;label:string}[]>([]);
  const purchase = Object.fromEntries(Object.entries(loadout).filter(([name,count])=>unlocked(round).includes(name)&&count>0));
  const spent = Object.entries(purchase).reduce((sum,[name,count])=>sum+COSTS[name]*count,0);
  const budget = (round==='round1'?0:10)+(round==='final'&&advanced&&carryover?carryover.points:0);
  const [battle,setBattle] = useState('');
  const [frames,setFrames] = useState<Frame[]>([]);
  const [cursor,setCursor] = useState(0);
  const [playing,setPlaying] = useState(false);
  const [speed,setSpeed] = useState(1);
  const seekSerial = useRef(0);
  const battleSerial = useRef(0);
  const [busy,setBusy] = useState(false);
  const [stepping,setStepping] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [matches,setMatches] = useState(100);
  const [pool,setPool] = useState('development');
  const [job,setJob] = useState<Job|null>(null);
  const [jobs,setJobs] = useState<Job[]>([]);
  const [source,setSource] = useState<string|null>(null);
  const [label,setLabel] = useState('');
  const advancing = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const frame = frames[cursor] ?? null;
  useEffect(()=>{api<{id:string;points:number;label:string}[]>('/armory/carryover').then(setCarrySources).catch(()=>{});},[battle,frame?.finished]);

  async function refresh() { const list = await api<Version[]>('/versions'); setVersions(list); setVersion(v => v || list[0]?.id || ''); }
  useEffect(() => {refresh().catch(e => setError(String(e))); api<Job[]>('/benchmarks').then(setJobs).catch(e => setError(String(e)));}, []);
  useEffect(() => {
    const serial = battleSerial.current;
    let mounted = true;
    api<{id:string;frame:Frame}|null>('/battles/active').then(async active => {
      if (active && mounted && serial===battleSerial.current) {
        const recorded=await Promise.all(Array.from({length:active.frame.tick+1},(_,tick)=>api<Frame>(`/battles/${active.id}/frames/${tick}`)));
        if(mounted && serial===battleSerial.current){setBattle(active.id); setFrames(recorded); setCursor(recorded.length-1);}
      }
    }).catch(() => {});
    return ()=>{mounted=false;};
  }, []);
  useEffect(() => {
    if (!job || job.status !== 'running') return;
    let active = true;
    const timer = setInterval(() => {api<Job>(`/benchmarks/${job.id}`).then(j => {if(active) {setJob(j); setJobs(old => [...old.filter(x => x.id !== j.id),j]);}}).catch(e => {if(active) setError(String(e));});}, 1000);
    return () => {active = false; clearInterval(timer);};
  }, [job?.id,job?.status]);

  async function advance() {
    if (advancing.current || busy) return;
    if (cursor < frames.length-1) {setCursor(c => c+1); return;}
    if (!battle || frame?.finished) {setPlaying(false); return;}
    const expectedSeek = seekSerial.current;
    advancing.current = true;
    setStepping(true);
    try {const next = await api<Frame>(`/battles/${battle}/step`, {expected_tick:frame?.tick}); setFrames(old => old.some(f=>f.tick===next.tick)?old:[...old,next]); if(seekSerial.current===expectedSeek)setCursor(next.tick); if(next.finished) {setPlaying(false);if(next.armory?.round==='round2'&&!next.abandoned)setCarryover({id:battle,points:next.armory.remaining_points});}}
    catch(e) {setError(String(e)); setPlaying(false);}
    finally {advancing.current = false;setStepping(false);}
  }
  useEffect(() => {if (!playing||stepping) return; const timer = setTimeout(() => {void advance();}, 300/speed); return () => clearTimeout(timer);},[playing,stepping,cursor,frames.length,speed,battle]);
  const seek=useCallback((tick:number)=>{seekSerial.current++;setPlaying(false);setCursor(Math.max(0,Math.min(tick,frames.length-1)));},[frames.length]);
  const finalFrame = frames.length&&frames[frames.length-1].finished?frames[frames.length-1]:null;
  const canNext = cursor<frames.length-1 || Boolean(battle&&!frame?.finished);

  async function guarded(action: () => Promise<void>) {setBusy(true); setError(''); try {await action();} catch(e) {setError(String(e));} finally {setBusy(false);}}
  async function upload(file?: File) {if(!file) return; await guarded(async () => {if(file.size > 262144) throw new Error('Upload a Python file up to 256 KiB'); const bytes = new Uint8Array(await file.arrayBuffer()); new TextDecoder('utf-8',{fatal:true}).decode(bytes); const encoded = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join('')); const result = await api<Version>('/versions', {filename:file.name, source_base64:encoded,label:file.name}); await refresh(); setVersion(result.id);setSource(null); setNotice('Source preserved as a version.');});}
  async function startBattle() {if(advancing.current||busy)return;battleSerial.current++;seekSerial.current++;setPlaying(false); await guarded(async () => {if(battle&&battle!==carryover?.id) await api(`/battles/${battle}`,undefined,'DELETE'); setBattle(''); setFrames([]); setCursor(0); const result = await api<{id:string;seed:number;frame:Frame}>('/battles',{version,seed:reproducible?seed:null,teams,round,difficulty,loadout:purchase,carryover_from:carryover?.id,advanced:round==='final'&&advanced});if(result.seed!==undefined)setSeed(result.seed); setBattle(result.id); setFrames([result.frame]); setCursor(0);});}
  async function startBenchmark() {await guarded(async () => {const result = await api<Job>('/benchmarks',{versions:[version,...(comparison && comparison !== version ? [comparison] : [])],matches,teams,round,pool,master_seed:seed,difficulty,loadout:purchase}); setJob(result); setJobs(old => [...old,result]);});}
  const versionName = (path: string) => {const id = path.split(/[\\/]/).pop()!; return versions.find(v => v.id === id)?.label ?? id.slice(0,12);};

  return <div className="app"><header><a className="brand" href="#"><span className="brand-mark">⌖</span><span>BATTLESHIP<span className="brand-sub">STRATEGY LAB</span></span></a><div className="header-right"><span className="local-dot"/>LOCAL WORKSPACE <span className="badge">APPROXIMATE ENGINE</span></div></header>
    <div className="intro"><div><span className="eyebrow">OBSERVE. COMPARE. ITERATE.</span><h1>Your strategy, under fire.</h1><p>Import a bot, inspect a battle, and test what holds up across seeds.</p></div><div className="intro-counter">40<span>×</span>40<small>ONE SHARED SEA</small></div></div>
    <nav aria-label="Workspace"><button className={tab === 'battle' ? 'active' : ''} onClick={() => {setTab('battle');if(round==='all') setRound('round1');}}>01 / Battle room</button><button className={tab === 'benchmark' ? 'active' : ''} onClick={() => {setPlaying(false); setTab('benchmark');}}>02 / Benchmarks</button><button className={tab === 'versions' ? 'active' : ''} onClick={() => {setPlaying(false);setTab('versions');}}>03 / Strategy library <span>{versions.length}</span></button><button className={tab === 'diagnostics' ? 'active' : ''} onClick={() => {setPlaying(false);setTab('diagnostics');}}>04 / Diagnostics & history</button></nav>
    {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>Dismiss</button></div>}{notice && <div role="status" className="notice">{notice}</div>}
    <div className="layout"><aside><span className="eyebrow">RUN CONFIGURATION</span><h2>Set the conditions</h2>
      <label>Strategy version<select value={version} onChange={e => {setVersion(e.target.value); setSource(null);}}><option value="">Select a strategy</option>{versions.map(v => <option value={v.id} key={v.id}>{v.label} · {v.id.slice(0,8)}</option>)}</select></label>
      <input aria-label="Upload strategy.py" ref={fileInput} type="file" accept=".py" hidden onChange={e => {void upload(e.target.files?.[0]); e.target.value='';}}/><button className="secondary full" disabled={busy} onClick={() => fileInput.current?.click()}>＋ Upload strategy.py</button>
      <div className="divider"/><label>Round<select value={round} onChange={e => setRound(e.target.value)}><option value="round1">Round 1 · no boosters</option><option value="round2">Round 2 · flare / cluster</option><option value="final">Final · all boosters</option>{tab === 'benchmark' && <option value="all">All rounds</option>}</select></label>
      <label>Opponents<select value={difficulty} onChange={e => setDifficulty(e.target.value)}>{['Easy · Random Shooter','Medium · Hunt Target','Hard · Parity Hunter','Expert · Probability Hunter','Extreme · Competitive Optimizer'].map((d,i) => <option key={d} value={['easy','medium','hard','expert','extreme'][i]}>{d}</option>)}</select></label>
      <div className="input-pair"><label>Teams<input type="number" min="2" max="20" value={teams} onChange={e => setTeams(Number(e.target.value))}/></label><label>Seed<input type="number" value={seed} onChange={e => setSeed(Number(e.target.value))}/></label></div>
      <label className="check-label"><input type="checkbox" checked={reproducible} onChange={e=>setReproducible(e.target.checked)}/>Reuse seed (reproducible battle)</label><p className="fine">Unchecked: new randomized map and wind each battle. Checked: reuse the shown seed.</p><Armory round={round} loadout={purchase} onChange={setLoadout} carryover={tab==='battle'?carryover:null} advanced={tab==='battle'&&advanced} onAdvanced={setAdvanced} sources={tab==='battle'?carrySources:[]} onSource={id=>{setCarryover(carrySources.find(s=>s.id===id)??null);setAdvanced(false);}}/>
      <p className="fine">Opponents use private bot observations. The viewer reveals the full sea for analysis.</p>
      {tab === 'battle' && <button className="primary full" disabled={!version || busy || stepping || spent>budget || round==='all' || advancing.current} onClick={() => void startBattle()}>{busy ? 'Preparing…' : 'Create battle →'}</button>}
      <div className="aside-note"><b>Local approximation</b><p>Official engine unavailable. Wind, placement, and results follow the documented local model.</p></div>
    </aside><main>{tab === 'diagnostics' && <Diagnostics battle={battle}/>}
    {tab === 'battle' && <><div className="toolbar"><div><span className="eyebrow">{cursor < frames.length-1 ? 'REPLAY' : frame?.finished ? 'BATTLE COMPLETE' : 'LIVE SESSION'}</span><h2>Tick {frame?.tick ?? '—'} <span className="muted">/ 120</span></h2></div></div>
      <Board frame={frame} history={frames} speed={speed}/><ReplayTimeline tick={cursor} maxTick={Math.max(0,frames.length-1)} playing={playing} speed={speed} disabled={!frames.length||busy} canNext={canNext&&!stepping} onSeek={seek} onNext={()=>{setPlaying(false);void advance();}} onToggle={()=>setPlaying(!playing)} onSpeed={setSpeed}/><BattleResults finalFrame={finalFrame}/>
      <div className="team-list">{frame?.teams.map(t => <div className="team-card" key={t.seat}><span className="team-chip" style={{background:teamColor(t.seat)}}>{t.seat}</span><div><b>{t.seat==='A' ? 'Your strategy' : `Opponent ${t.seat}`}</b><small>{t.eliminated ? 'Eliminated' : !t.connected ? 'Disconnected' : `${t.ships.filter(s => !s.sunk).length} ships afloat`}</small></div><strong>{t.score}<small>PTS</small></strong><BoosterDetails team={t}/></div>)}</div>
      {frame?.armory&&<p className="fine">Team A {frame.armory.expired?'expired inventory':'current inventory'}: {Object.entries(frame.armory.inventory).map(([name,count])=>`${name} ${count}`).join(' · ')} · Unspent purchase points: {frame.armory.remaining_points}</p>}
      {frame?.runtime_error&&<p role="alert" className="error">{frame.runtime_error}</p>}
      {frame && <p className="fine">Strategy: {frame.strategy_status} · {frame.abandoned ? 'Abandoned — no ranking' : frame.finished ? frame.ranking.map(r => `${r.rank}. ${r.seat} (${r.score} pts)`).join(' / ') : 'Every team acts simultaneously.'}</p>}
      {battle && <FailurePanel battle={battle} tick={playing?Math.floor((frames.length-1)/10)*10:frames.length-1} onJump={seek}/>}
      {!battle && <p className="empty">Upload a strategy and create a battle to begin. Play runs new ticks; Replay revisits recorded frames.</p>}</>}
    {tab === 'versions' && <><StrategyWorkbench versions={versions} version={version} difficulty={difficulty} onSaved={async saved=>{await refresh();setVersion(saved.id);setNotice('New strategy version saved.');}}/><section className="panel"><span className="eyebrow">PRESERVED SOURCE</span><h2>Strategy library</h2><p className="muted">Each upload is stored by content hash. Renaming a version keeps its source intact.</p>{versions.length === 0 && <p className="empty">No strategies yet. Upload a Python file to start.</p>}{versions.map(v => <div className="version-row" key={v.id}><div><b>{v.label}</b><code>{v.id.slice(0,16)} · {v.bytes ?? 0} bytes</code></div><button onClick={() => {setVersion(v.id);setLabel(v.label);setSource(null);}}>Select</button><a href={`/api/versions/${v.id}/source`}>Download</a></div>)}{version && <><label>Version label<input value={label} onChange={e => setLabel(e.target.value)} placeholder={versions.find(v => v.id===version)?.label}/></label><div className="controls"><button disabled={!label.trim() || busy} onClick={() => void guarded(async () => {await api(`/versions/${version}`, {label},'PATCH'); await refresh();setNotice('Version label saved.');})}>Save label</button><button onClick={() => void guarded(async () => {const response = await fetch(`/api/versions/${version}/source`);if(!response.ok) throw new Error('Could not read source'); setSource(await response.text());})}>View source</button></div>{source !== null && <PythonPreview source={source}/>}</>}</section></>}
    {tab === 'benchmark' && <><section className="panel"><span className="eyebrow">MEASURE ACROSS SEEDS</span><h2>Benchmark & compare</h2><p className="muted">Identical seeds and seats for every selected version. Intervals show uncertainty across matches.</p><div className="benchmark-options"><label>Compare with<select value={comparison} onChange={e => setComparison(e.target.value)}><option value="">Single strategy</option>{versions.filter(v => v.id !== version).map(v => <option value={v.id} key={v.id}>{v.label} · {v.id.slice(0,8)}</option>)}</select></label><label>Matches per round<input type="number" min="1" max="1000" value={matches} onChange={e => setMatches(Number(e.target.value))}/></label><label>Seed pool<select value={pool} onChange={e => setPool(e.target.value)}><option value="development">Development</option><option value="holdout">Holdout validation</option></select></label></div><p className="fine">Tune on development. Freeze your versions before using holdout. Jobs may take several minutes.</p><button className="primary" disabled={!Number.isInteger(matches) || matches<1 || matches>1000 || !version || busy || spent>(round==='round1'?0:10) || job?.status==='running'} onClick={() => void startBenchmark()}>Run benchmark →</button>
      {job?.status==='running' && <div className="progress" role="status"><progress value={job.done ?? 0} max={job.total ?? 100}/><span>{job.done ?? 0} / {job.total ?? '—'} matches complete</span></div>}{job?.status==='failed' && <p role="alert" className="error">{job.error}</p>}
      <label>Saved runs<select value={job?.id ?? ''} onChange={e => {if(e.target.value) void guarded(async () => setJob(await api<Job>(`/benchmarks/${e.target.value}`)));}}><option value="">Select a report</option>{jobs.map(j => <option value={j.id} key={j.id}>{j.id.slice(0,10)} · {j.status}</option>)}</select></label></section>
      {job?.report && <><div className="report-heading"><h2>Results · {job.report.pool}</h2><a href={`/api/benchmarks/${job.id}`} download="benchmark.json">Download report ↗</a></div>{Object.entries(job.report.rounds).map(([name,result]) => <section className="panel" key={name}><h3>{name.toUpperCase()} <span className="muted">· {job.report!.teams} teams · {job.report!.opponent}</span></h3><div className="table-wrap"><table><thead><tr><th>Version</th><th>Win rate</th><th>Mean rank</th><th>Mean score</th><th>Mean waste</th><th>Mean timeouts</th></tr></thead><tbody>{result.strategies.map(s => <tr key={s.version}><td>{versionName(s.version)}<small>{s.summary.matches} matches / {s.summary.abandoned} abandoned / {s.summary.timeouts_total} timeouts</small></td><td>{estimate(s.summary.win_rate,true)}</td><td>{estimate(s.summary.rank)}</td><td>{estimate(s.summary.score)}</td><td>{estimate(s.summary.wasted_shots)}</td><td>{estimate(s.summary.timeouts)}</td></tr>)}</tbody></table></div><p className="fine">Parentheses: 95% confidence interval. Wilson for wins; normal approximation for means.</p>{result.comparisons.map((c,i) => <div className="comparison" key={i}><h4>{versionName(c.left)} minus {versionName(c.right)}</h4><p>{c.paired_matches} paired matches · Positive score / win differences favor the first version; lower rank / waste / timeouts favor it.</p><div className="table-wrap"><table><thead><tr><th>Win-rate difference</th><th>Rank difference</th><th>Score difference</th><th>Waste difference</th><th>Timeout difference</th></tr></thead><tbody><tr><td>{estimate(c.win,true)}</td><td>{estimate(c.rank)}</td><td>{estimate(c.score)}</td><td>{estimate(c.wasted_shots)}</td><td>{estimate(c.timeouts)}</td></tr></tbody></table></div></div>)}</section>)}</>}
    </>}
    </main></div><footer>STRATEGY LAB / LOCAL EDITION <span>Simulation results are approximate. Run only strategies you trust.</span></footer></div>;
}
