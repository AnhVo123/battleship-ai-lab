import { useEffect, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import type { Version } from './types';

type Validation = {valid:boolean;errors:{line:number|null;message:string}[];note?:string};
type Opponent = {name:string;official:boolean;algorithm:string;source?:string;note:string};

export function PythonPreview({source}:{source:string}) {return <CodeMirror value={source} height="360px" theme="dark" extensions={[python()]} editable={false}/>;}

export default function StrategyWorkbench({versions,version,difficulty,onSaved}:{versions:Version[];version:string;difficulty:string;onSaved:(version:Version)=>Promise<void>}) {
  const [source,setSource]=useState('');
  const [label,setLabel]=useState('');
  const [validation,setValidation]=useState<Validation|null>(null);
  const [opponent,setOpponent]=useState<Opponent|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [editing,setEditing]=useState(true);
  const [dirty,setDirty]=useState(false);
  useEffect(()=>{let active=true;setError('');setValidation(null);setDirty(false);
    fetch(version?`/api/versions/${version}/source`:'/api/strategy-template').then(async response=>{if(!response.ok)throw new Error('Could not load source');return response.text();}).then(text=>{if(active){setSource(text);setLabel(versions.find(v=>v.id===version)?.label ?? 'New strategy');}}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};
  },[version]);
  useEffect(()=>{let active=true;fetch(`/api/opponents/${difficulty}`).then(async response=>{if(!response.ok)throw new Error('Could not load opponent preview');return response.json() as Promise<Opponent>;}).then(value=>{if(active)setOpponent(value);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[difficulty]);
  async function check(runtime=false) {const response=await fetch(runtime?'/api/validate-runtime':'/api/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source})});if(!response.ok)throw new Error('Validation request failed');const value=await response.json() as Validation;setValidation(value);return value.valid;}
  async function save() {setBusy(true);setError('');try{if(!await check())return;const response=await fetch('/api/versions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:'strategy.py',source,label})});const value=await response.json();if(!response.ok)throw new Error(JSON.stringify(value.detail));await onSaved(value);setDirty(false);}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="panel"><span className="eyebrow">EDIT · VALIDATE · PRESERVE</span><h2>Strategy editor & comparison</h2><p className="fine">Paste or edit Python. Saving creates a content-addressed version; existing source is preserved. Unsaved edits remain in this editor until you select another version.</p>
    {error&&<p role="alert" className="error">{error}</p>}
    <label>New version label<input value={label} onChange={e=>setLabel(e.target.value)}/></label>
    <div className="controls"><button disabled={busy} onClick={()=>{setBusy(true);check().catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Validate strategy</button><button disabled={busy} onClick={()=>{setBusy(true);check(true).catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Check runtime imports</button><button disabled={busy} onClick={()=>void save()}>Save as new version</button><button onClick={()=>setEditing(!editing)}>{editing?'Read-only preview':'Edit / paste source'}</button><button disabled={busy} onClick={()=>{fetch('/api/strategy-template').then(r=>r.text()).then(text=>{setSource(text);setDirty(true);setValidation(null);setLabel('Template strategy');}).catch(e=>setError(String(e)));}}>Load working template</button></div>
    <p role="status" className="fine">{dirty?'Unsaved source changes':'Source loaded'} · {editing?'Editable Python':'Read-only Python preview'}</p>
    {validation&&<div className={validation.valid?'notice':'error'} role={validation.valid?'status':'alert'}>{validation.valid?'Syntax, imports and interface checks passed.':validation.errors.map((e,i)=><div key={i}>{e.line?`Line ${e.line}: `:''}{e.message}</div>)}<p className="fine">{validation.note}</p></div>}
    <div className="source-comparison"><div><h3>Player · {label}</h3><CodeMirror aria-label="Player strategy Python editor" value={source} height="460px" theme="dark" extensions={[python()]} editable={editing} onChange={text=>{setSource(text);setDirty(true);setValidation(null);}}/></div><div><h3>{opponent?.name ?? 'Opponent'} · {opponent?.official?'Official':'Custom local implementation'}</h3><p className="fine">{opponent?.algorithm} {opponent?.note}</p><CodeMirror aria-label="Opponent Python source preview" value={opponent?.source ?? opponent?.algorithm ?? 'Loading opponent preview…'} height="460px" theme="dark" extensions={[python()]} editable={false}/></div></div>
    <details><summary>Bot interface and runtime rules</summary><p className="fine">Import Bot from arena_sdk and define MyBot(Bot).on_state(self, state). Return one action with an alive ship, dir 0–360, elev 0–90, and integer power 1–state.config.physics.power_max. Integer ship indices are zero-based in the local adapter; the supplied README uses ship["ship"] name identifiers, which remain supported. Every shot starts at cells[0]. Optional actions: flare, cluster, torpedo, teleport; all aim keys are still required. An empty booster falls back to a plain shot. self is preserved between ticks and reset for each battle. Runtime exceptions and invalid actions are shown in battle diagnostics. Hidden referee state is never part of the bot observation.</p></details>
  </section>;
}
