import { useState } from 'react';
import { PythonPreview } from './LazyStrategy';
import type { Team } from './types';

export function StrategyDetails({team,player}:{team:Team;player?:Team}) {
  const [open,setOpen]=useState(false);
  const strategy=team.strategy;
  if(!strategy)return <small>Strategy unavailable in this recording</small>;
  return <div><small>{strategy.level ? `${strategy.level} · ` : ''}{strategy.name} · {strategy.type} · {strategy.official?'Official built-in bot':strategy.implementation==='local_approximation'?'Custom built-in · local approximation':'Custom bot'}</small>
    <button aria-expanded={open} onClick={()=>setOpen(!open)}>View Strategy</button>
    {open&&<div><p className="fine">{strategy.algorithm} {strategy.note} {strategy.level&&`Active policy: Opponent(level="${strategy.level}").`}</p><div className="source-comparison">
      {team.seat!=='A'&&<div><h3>My strategy.py · {player?.strategy?.name??'Player'}</h3>{player?.strategy?.source?<PythonPreview source={player.strategy.source}/>:<p>Player source unavailable in this recording.</p>}</div>}
      <div><h3>{team.name??team.seat} · {strategy.name}</h3>{strategy.source?<PythonPreview source={strategy.source}/>:<p>{strategy.algorithm??'Source unavailable in this recording.'}</p>}</div>
    </div></div>}
  </div>;
}

export default function BattleStrategies({teams}:{teams:Team[]}) {
  return <section className="panel"><h2>Battle strategies</h2>{teams.filter(t=>t.seat!=='A').map(team=><div className="version-row" key={team.seat}><div><b>{team.name??`Opponent ${team.seat}`}</b><StrategyDetails team={team} player={teams.find(t=>t.seat==='A')}/></div></div>)}</section>;
}
