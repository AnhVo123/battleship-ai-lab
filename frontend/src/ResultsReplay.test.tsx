// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import ReplayTimeline from './ReplayTimeline';
import BattleResults, {RankingTable, BoosterDetails} from './BattleResults';
import App from './App';
import type { Frame } from './types';

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();});
const initial:Frame={tick:0,finished:false,abandoned:false,wind:[0,0],traces:[],teams:[],strategy_status:'ready',ranking:[]};
const final:Frame={...initial,tick:2,finished:true,history_id:'history1',ranking:[{rank:1,seat:'B',name:'Hunt Target · B',score:5,wasted:10,ships_remaining:4},{rank:2,seat:'A',name:'My team',score:3,wasted:12,ships_remaining:2}]};

describe('ranking and replay controls',()=>{
  it('plays the final recorded ticks at 4x without generating new actions',async()=>{
    const mock=vi.spyOn(globalThis,'fetch').mockImplementation(async input=>{
      const path=String(input);
      if(path==='/api/versions')return new Response('[{"id":"v","label":"Test"}]');
      if(path==='/api/battles/active')return new Response(JSON.stringify({id:'recorded',frame:{...initial,tick:120,finished:true}}));
      if(path.includes('/frames/')){const tick=Number(path.split('/').pop());return new Response(JSON.stringify({...initial,tick,finished:tick===120}));}
      if(path.endsWith('/diagnostics'))return new Response('{"findings":[]}');
      return new Response('[]');
    });
    render(<App/>);
    await waitFor(()=>expect(screen.getByRole('heading',{name:'Tick 120 / 120'})).toBeTruthy());
    fireEvent.change(screen.getByRole('slider',{name:'Replay tick'}),{target:{value:'115'}});
    fireEvent.change(screen.getByRole('combobox',{name:'Playback speed'}),{target:{value:'4'}});
    fireEvent.click(screen.getByRole('button',{name:'▶ Play'}));
    await waitFor(()=>expect(screen.getByRole('heading',{name:'Tick 120 / 120'})).toBeTruthy(),{timeout:3000});
    await waitFor(()=>expect(screen.getByRole('button',{name:'▶ Play'})).toBeTruthy());
    expect(mock.mock.calls.filter(([url])=>String(url).endsWith('/step'))).toHaveLength(0);
  });
  it('shows purchases, consumption, expiration and measured effectiveness',async()=>{
    render(<BoosterDetails team={{seat:'B',score:4,wasted:0,eliminated:false,connected:true,ships:[],shots:[],boosters:{purchased:{torpedo:1,cluster:3},remaining:{torpedo:0,cluster:2},expired:true,remaining_points:0,stats:{torpedo:{used:1,points:4,hits:2,sinks:1,revealed:0},cluster:{used:1,points:0,hits:0,sinks:0,revealed:0}}}}}/>);
    fireEvent.click(screen.getByText('Boosters · 2 used'));
    const table=await screen.findByRole('table',{name:'B booster statistics'});
    expect(table.textContent).toContain('Expired');
    expect(table.textContent).toContain('torpedo1104210');
  });
  it('shows official server order and highlights my team with ships remaining',()=>{
    render(<RankingTable ranking={final.ranking} teams={[]}/>);
    const rows=within(screen.getByRole('table',{name:'Final team ranking'})).getAllByRole('row');
    expect(rows[1].textContent).toContain('Hunt Target');
    expect(rows[2].className).toBe('your-result');
    expect(within(rows[2]).getAllByRole('cell').map(e=>e.textContent)).toEqual(['2','AMy teamYOU','3','2','Unavailable in this recording','Unavailable']);
  });
  it('supports direct seeking, previous/next, restart, pause, and speed selection',()=>{
    const next=vi.fn();
    function Wrapper(){const [tick,setTick]=useState(5),[playing,setPlaying]=useState(true),[speed,setSpeed]=useState(1);return <ReplayTimeline tick={tick} maxTick={10} playing={playing} speed={speed} disabled={false} canNext={tick<10} onSeek={t=>{setTick(t);setPlaying(false);}} onNext={()=>{next();setTick(tick+1);}} onToggle={()=>setPlaying(!playing)} onSpeed={setSpeed}/>;}
    render(<Wrapper/>);
    const slider=screen.getByRole('slider',{name:'Replay tick'});
    expect((slider as HTMLInputElement).disabled).toBe(false); // seek while playing
    fireEvent.change(slider,{target:{value:'8'}});
    expect(screen.getByText('Tick 8 / 10')).toBeTruthy();
    expect(screen.getByRole('button',{name:'▶ Play'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'← Previous'}));
    expect(screen.getByText('Tick 7 / 10')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Next →'}));
    expect(next).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByRole('combobox',{name:'Playback speed'}),{target:{value:'4'}});
    expect((screen.getByRole('combobox',{name:'Playback speed'}) as HTMLSelectElement).value).toBe('4');
    fireEvent.click(screen.getByRole('button',{name:'↺ Restart'}));
    expect(screen.getByText('Tick 0 / 10')).toBeTruthy();
    expect((screen.getByRole('button',{name:'← Previous'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('does not request removed battle history or show completed battle controls',()=>{
    const fetchMock=vi.spyOn(globalThis,'fetch').mockRejectedValue(new Error('History endpoint unavailable'));
    const {rerender}=render(<BattleResults finalFrame={null}/>);
    expect(screen.queryByRole('combobox',{name:'Battle history'})).toBeNull();
    expect(screen.queryByText('Refresh history')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    rerender(<BattleResults finalFrame={final}/>);
    expect(screen.getByRole('table',{name:'Final team ranking'})).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('suppresses scores and ranks for an abandoned battle',()=>{
    render(<RankingTable ranking={[]} teams={[]} abandoned/>);
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.getByRole('status').textContent).toContain('Battle abandoned');
  });
  it('retains a sought tick when a pending live step completes and automatically shows final ranks',async()=>{
    let finish:((response:Response)=>void)|undefined;
    let steps=0;
    vi.spyOn(globalThis,'fetch').mockImplementation(async (input,init)=>{
      const path=String(input);
      if(path==='/api/versions')return new Response('[{"id":"a","label":"My team"}]');
      if(path==='/api/battles'&&init?.method==='POST')return new Response(JSON.stringify({id:'live',frame:initial}));
      if(path.endsWith('/diagnostics'))return new Response('{"findings":[]}');
      if(path.endsWith('/step')){
        if(++steps===1)return new Response(JSON.stringify({...initial,tick:1}));
        return new Promise<Response>(resolve=>{finish=resolve;});
      }
      return new Response('[]');
    });
    render(<App/>);
    await waitFor(()=>expect((screen.getByRole('button',{name:'Create battle →'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Create battle →'}));
    await waitFor(()=>expect(screen.getByRole('heading',{name:'Tick 0 / 120'})).toBeTruthy());
    fireEvent.click(screen.getByRole('button',{name:'Next →'}));
    await waitFor(()=>expect(screen.getByRole('heading',{name:'Tick 1 / 120'})).toBeTruthy());
    fireEvent.click(screen.getByRole('button',{name:'Next →'}));
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    fireEvent.change(screen.getByRole('combobox',{name:'Playback speed'}),{target:{value:'4'}});
    fireEvent.click(screen.getByRole('button',{name:'Next →'}));
    expect(steps).toBe(2);
    fireEvent.change(screen.getByRole('slider',{name:'Replay tick'}),{target:{value:'0'}});
    await act(async()=>{finish!(new Response(JSON.stringify(final)));});
    expect(screen.getByRole('heading',{name:'Tick 0 / 120'})).toBeTruthy();
    expect(screen.getByRole('table',{name:'Final team ranking'})).toBeTruthy();
    expect(screen.getByText(/Automatically saved to battle history/)).toBeTruthy();
  });
});
