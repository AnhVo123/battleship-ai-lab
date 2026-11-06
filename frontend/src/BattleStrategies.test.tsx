// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import BattleStrategies from './BattleStrategies';
import {RankingTable} from './BattleResults';
import type {Team} from './types';
vi.mock('./StrategyWorkbench',()=>({PythonPreview:({source}:{source:string})=><pre>{source}</pre>}));
afterEach(cleanup);
const base={score:0,wasted:0,eliminated:false,connected:true,ships:[],shots:[]};
const teams:Team[]=[{...base,seat:'A',name:'Saved player',strategy:{name:'Original version',type:'MyBot',level:null,official:false,implementation:'custom_strategy',source:'class MyBot: pass'}},...['B','C'].map(seat=>({...base,seat,name:`Hunt Target ${seat}`,strategy:{name:'Hunt Target',type:'Opponent',level:'medium',official:false,implementation:'local_approximation',source:'class Opponent: actual_source',algorithm:'Pursue hit neighbours'}}))];
it('lists every opponent and compares recorded sources side by side',async()=>{
 render(<BattleStrategies teams={teams}/>);
 expect(screen.getAllByRole('button',{name:'View Strategy'})).toHaveLength(2);
 expect(screen.getAllByText(/medium.*Hunt Target.*Opponent.*Custom built-in/)).toHaveLength(2);
 fireEvent.click(screen.getAllByRole('button',{name:'View Strategy'})[1]);
 expect(await screen.findByText('class MyBot: pass')).toBeTruthy();
 expect(await screen.findByText('class Opponent: actual_source')).toBeTruthy();
 expect(screen.getByText(/Active policy: Opponent/)).toBeTruthy();
});
it('shows actual strategy in rankings and distinguishes official provenance',async()=>{
 render(<RankingTable teams={[teams[0],{...teams[1],strategy:{...teams[1].strategy!,official:true}}]} ranking={[{rank:1,seat:'B',score:0,wasted:0}]}/>);
 expect(screen.getByText(/Official built-in bot/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'View Strategy'}));
 expect(await screen.findByText('class Opponent: actual_source')).toBeTruthy();
});
it('does not invent strategies for older recordings',()=>{
 render(<BattleStrategies teams={[{...base,seat:'B',name:'Old opponent'}]}/>);
 expect(screen.getByText('Strategy unavailable in this recording')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'View Strategy'})).toBeNull();
});
