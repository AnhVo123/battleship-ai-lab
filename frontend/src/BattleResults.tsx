import type { Frame, RankingRow, Team } from './types';
import { teamColor } from './types';
import { StrategyDetails } from './BattleStrategies';
import { memo, useState } from 'react';

export function BoosterDetails({team}:{team:Team}) {
  const [open,setOpen]=useState(false);
  if(!team.boosters)return <span>Unavailable in this recording</span>;
  const {purchased,remaining,stats,expired,remaining_points}=team.boosters;
  return <details className="booster-details" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Boosters · {Object.values(stats).reduce((n,s)=>n+s.used,0)} used</summary>
    <p>{remaining_points} unspent points · {expired?'Unused inventory expired':'Inventory available'}</p>
    {open&&<table aria-label={`${team.seat} booster statistics`}><thead><tr><th>Booster</th><th>Bought</th><th>Used</th><th>{expired?'Expired':'Left'}</th><th>Points</th><th>Hits</th><th>Sinks</th><th>Revealed</th></tr></thead><tbody>{Object.entries(purchased).map(([kind,count])=><tr key={kind}><th>{kind}</th><td>{count}</td><td>{stats[kind]?.used??0}</td><td>{remaining[kind]??0}</td><td>{stats[kind]?.points??0}</td><td>{stats[kind]?.hits??0}</td><td>{stats[kind]?.sinks??0}</td><td>{stats[kind]?.revealed??0}</td></tr>)}</tbody></table>}
  </details>;
}


export function RankingTable({ranking,teams,abandoned=false}:{ranking:RankingRow[];teams:Team[];abandoned?:boolean}) {
  if(abandoned)return <p role="status">Battle abandoned: the official rules suppress scores and ranks when all seats disconnect.</p>;
  return <div className="table-wrap"><table aria-label="Final team ranking"><thead><tr><th>Rank</th><th>Team</th><th>Score</th><th>Ships remaining</th><th>Strategy</th><th>Boosters</th></tr></thead><tbody>{ranking.map(row=>{
    const team=teams.find(t=>t.seat===row.seat);
    return <tr key={row.seat} className={row.seat==='A'?'your-result':''} aria-label={row.seat==='A'?'Your team result':undefined}><td>{row.rank}</td><td><span className="result-seat" style={{background:teamColor(row.seat)}}>{row.seat}</span>{row.name??team?.name??(row.seat==='A'?'Your strategy':`Opponent ${row.seat}`)}{row.seat==='A'&&<strong className="your-tag">YOU</strong>}</td><td>{row.score}</td><td>{row.ships_remaining??team?.ships.filter(s=>!s.sunk).length??0}</td><td>{team?<StrategyDetails team={team} player={teams.find(t=>t.seat==='A')}/>: 'Unavailable in this recording'}</td><td>{team?<BoosterDetails team={team}/>: 'Unavailable'}</td></tr>;
  })}</tbody></table></div>;
}

function BattleResults({finalFrame}:{finalFrame:Frame|null}) {
  if(!finalFrame)return null;
  return <section className="panel battle-results"><span className="eyebrow">POST-BATTLE RESULTS</span><h2>Final ranking</h2>
    <RankingTable ranking={finalFrame.ranking} teams={finalFrame.teams} abandoned={finalFrame.abandoned}/>
    <p className="fine">{finalFrame.history_id?'Automatically saved to battle history.':'Results from the recorded battle.'} Ranking: joined seats first, score descending, fewer wasted shots, earlier last sinking, earlier final point, earlier first point, then seat letter.</p>
  </section>;
}

export default memo(BattleResults);
