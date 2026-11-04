// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import Board from './Board';
import { estimate } from './types';
import type { Frame } from './types';

afterEach(() => {cleanup();vi.restoreAllMocks();});
const frame: Frame = {tick:0,finished:false,abandoned:false,wind:[.2,-.4],traces:[],strategy_status:'ready',ranking:[],teams:[{seat:'A',score:0,wasted:0,eliminated:false,connected:true,ships:[{name:'destroyer',cells:[[2,3],[2,4]],holes:[[2,3]],sunk:false}],shots:[]}]};

describe('battle viewer', () => {
  it('renders ships, wind and grid with accessible labels', () => {
    render(<Board frame={frame}/>);
    expect(screen.getByRole('img',{name:'40 by 40 battle board'})).toBeTruthy();
    expect(screen.getByText('0.20, -0.40')).toBeTruthy();
    expect(document.querySelectorAll('.sea rect').length).toBeGreaterThan(3);
  });
  it('steps, replays, plays and pauses without changing recorded frames', async () => {
    const mock = vi.spyOn(globalThis,'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/versions') return new Response(JSON.stringify([{id:'a',label:'Baseline',bytes:100}]));
      if (['/api/benchmarks','/api/battle-history','/api/armory/carryover'].includes(url)) return new Response('[]');
      if(url.endsWith('/diagnostics'))return new Response('{"findings":[]}');
      if (url === '/api/battles') return new Response(JSON.stringify({id:'battle',frame}));
      if (url.endsWith('/step')) return new Response(JSON.stringify({...frame,tick:1}));
      throw new Error(`Unexpected ${url} ${init?.method}`);
    });
    render(<App/>);
    await waitFor(() => expect((screen.getByRole('button',{name:'Create battle →'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Create battle →'}));
    await waitFor(() => expect(screen.getByText('Tick 0')).toBeTruthy());
    fireEvent.click(screen.getByRole('button',{name:'Next →'}));
    await waitFor(() => expect(screen.getByText('Tick 1')).toBeTruthy());
    fireEvent.click(screen.getByRole('button',{name:'↺ Restart'}));
    expect(screen.getByText('Tick 0')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'▶ Play'}));
    expect(screen.getByRole('button',{name:'Ⅱ Pause'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Ⅱ Pause'}));
    expect(screen.getByRole('button',{name:'▶ Play'})).toBeTruthy();
    expect(mock.mock.calls.filter(([url]) => String(url).endsWith('/step')).length).toBe(1);
  });
  it('surfaces API errors', async () => {
    vi.spyOn(globalThis,'fetch').mockImplementation(async input=>String(input)==='/api/battle-history'?new Response('[]'):new Response(JSON.stringify({detail:'Server offline'}),{status:503}));
    render(<App/>);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Server offline'));
  });
  it('starts a paired benchmark with selected versions and renders stored confidence intervals', async () => {
    const metric = {mean:2,ci95:[1,3],n:100};
    const report = {engine_kind:'local_approximation',pool:'holdout',teams:2,opponent:'Hunt Target',rounds:{round1:{strategies:[{version:'/versions/a',summary:{matches:100,abandoned:0,win_rate:{rate:.5,ci95:[.4,.6],n:100},rank:metric,score:metric,wasted_shots:metric,timeouts:metric,timeouts_total:2}}],comparisons:[]}}};
    const fetchMock = vi.spyOn(globalThis,'fetch').mockImplementation(async (input, init) => {
      if(String(input)==='/api/versions') return new Response(JSON.stringify([{id:'a',label:'First'},{id:'b',label:'Second'}]));
      if(String(input)==='/api/benchmarks' && init?.method==='POST') return new Response(JSON.stringify({id:'run1',status:'complete',report}));
      if(String(input)==='/api/benchmarks') return new Response('[]');
      throw new Error(`Unexpected request ${input}`);
    });
    render(<App/>);
    fireEvent.click(screen.getByRole('button',{name:'02 / Benchmarks'}));
    await waitFor(() => expect((screen.getByRole('button',{name:'Run benchmark →'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByRole('combobox',{name:'Compare with'}),{target:{value:'b'}});
    fireEvent.change(screen.getByRole('combobox',{name:'Seed pool'}),{target:{value:'holdout'}});
    fireEvent.click(screen.getByRole('button',{name:'Run benchmark →'}));
    await waitFor(() => expect(screen.getByText('50.0% (40.0% – 60.0%)')).toBeTruthy());
    const request = fetchMock.mock.calls.find(([url,init]) => url==='/api/benchmarks' && init?.method==='POST');
    expect(JSON.parse(String(request?.[1]?.body)).versions).toEqual(['a','b']);
    expect(JSON.parse(String(request?.[1]?.body)).pool).toBe('holdout');
  });
  it('formats confidence intervals including zero and absent results', () => {
    expect(estimate({mean:0,ci95:[0,0],n:100})).toBe('0.00 (0.00 – 0.00)');
    expect(estimate({rate:.5,ci95:[.4,.6],n:100},true)).toContain('50.0%');
    expect(estimate({mean:null,ci95:[null,null],n:0})).toBe('—');
  });
});
