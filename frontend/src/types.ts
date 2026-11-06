export type Version = {id: string; label: string; bytes?: number};
export type Trace = {seat: string; kind: string; result: string; points: number[][]; landing: number[]; flight_seconds: number};
export type BattleStrategy = {name:string;type:string;level:string|null;official:boolean;implementation:string;source?:string;algorithm?:string;version?:string;note?:string};
export type Team = {seat: string; name?:string;score: number; wasted: number; eliminated: boolean; connected: boolean;
  boosters?:{purchased:Record<string,number>;remaining:Record<string,number>;expired:boolean;remaining_points:number;stats:Record<string,{used:number;points:number;hits:number;revealed:number;sinks:number}>};
  strategy?:BattleStrategy;ships: {name: string; cells: number[][]; holes: number[][]; sunk: boolean}[]; shots: (string | number)[][]};
export type RankingRow = {rank:number;seat:string;score:number;wasted:number;name?:string;ships_remaining?:number};
export type Frame = {tick: number; finished: boolean; abandoned: boolean; wind: number[]; traces: Trace[]; teams: Team[]; strategy_status: string;history_id?:string;
  events?:{seat:string;kind:string;ship:string;origin:number[];from_cells:number[][];cells:number[][];results:(string|number)[][];points:number;landing?:number[];sunk_cells?:number[][]}[];
  runtime_error?:string;armory?:{round:string;remaining_points:number;inventory:Record<string,number>;expired:boolean};
  ranking: RankingRow[]};
export type Estimate = {mean?: number | null; rate?: number | null; ci95: (number | null)[]; n: number};
export type Summary = {matches: number; abandoned: number; win_rate: Estimate; rank: Estimate; score: Estimate; wasted_shots: Estimate; timeouts: Estimate; timeouts_total: number};
export type Report = {engine_kind: string; pool: string; teams: number; opponent: string; rounds: Record<string, {
  strategies: {version: string; summary: Summary}[];
  comparisons: {left: string; right: string; paired_matches: number; win: Estimate; rank: Estimate; score: Estimate; wasted_shots: Estimate; timeouts: Estimate}[]}>};
export type Job = {id: string; status: string; done?: number; total?: number; error?: string; report?: Report};
export const colors = ['#63e6be','#ffa94d','#91a7ff','#f783ac','#74c0fc','#ffd43b','#da77f2','#a9e34b','#ff8787','#66d9e8', '#b2f2bb','#ffc078','#bac8ff','#fcc2d7','#a5d8ff','#ffec99','#eebefa','#d8f5a2','#ffc9c9','#c5f6fa'];
export const teamColor = (seat: string) => colors[seat.charCodeAt(0)-65] || '#fff';
export function estimate(value: Estimate | undefined, percent = false): string {
  if (!value) return '—';
  const number = value.mean ?? value.rate;
  if (number == null) return '—';
  const format = (n: number) => percent ? `${(n*100).toFixed(1)}%` : n.toFixed(2);
  return `${format(number)} (${value.ci95.map(n => n == null ? '—' : format(n)).join(' – ')})`;
}
