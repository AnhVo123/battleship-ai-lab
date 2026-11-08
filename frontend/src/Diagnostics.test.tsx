// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Diagnostics, { Findings } from './Diagnostics';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
const finding = {tick:3,classification:'confirmed_error',code:'exception',message:'Worker reported exception; no accepted action.',evidence:[{event:'seed:42/tick:3/seat:A',fields:['status']}]};

describe('evidence-based diagnostics',()=>{
  it('confirms deletion and clears the selected experiment',async()=>{
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false);
    const saved={id:'abc',kind:'battle',title:'Delete me',created_at:'2026-11-07',frames:[],diagnostics:{findings:[]}};
    const mock=vi.spyOn(globalThis,'fetch').mockImplementation(async(input,init)=>{
      if(init?.method==='DELETE')return new Response('{"deleted":true}');
      return new Response(JSON.stringify(String(input)==='/api/experiments'?[saved]:saved));
    });
    render(<Diagnostics battle=""/>);
    await screen.findByRole('option',{name:/Delete me/});
    fireEvent.change(screen.getByLabelText('Experiment history'),{target:{value:'abc'}});
    await screen.findByRole('heading',{name:'Delete me'});
    fireEvent.click(screen.getByRole('button',{name:'Delete experiment'}));
    expect(mock.mock.calls.some(([,init])=>init?.method==='DELETE')).toBe(false);
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button',{name:'Delete experiment'}));
    await waitFor(()=>expect(screen.queryByRole('heading',{name:'Delete me'})).toBeNull());
    expect(screen.queryByRole('option',{name:/Delete me/})).toBeNull();
    expect(mock.mock.calls.some(([url,init])=>url==='/api/experiments/abc'&&init?.method==='DELETE')).toBe(true);
  });
  it('filters hypotheses and jumps to an actual issue tick',()=>{
    const jump = vi.fn();
    render(<Findings diagnostic={{findings:[finding,{...finding,tick:4,classification:'hypothesis',message:'Review a zero-point booster.'}]}} onJump={jump}/>);
    fireEvent.click(screen.getByRole('button',{name:'Jump to tick 3'}));
    expect(jump).toHaveBeenCalledWith(3);
    fireEvent.change(screen.getByRole('combobox',{name:'Evidence classification'}),{target:{value:'hypothesis'}});
    expect(screen.queryByText(finding.message)).toBeNull();
    expect(screen.getByText('Review a zero-point booster.')).toBeTruthy();
  });
  it('loads experiment history, exposes exports and generates a copyable local prompt',async()=>{
    vi.spyOn(globalThis,'fetch').mockImplementation(async input=>{
      const path=String(input);
      if(path==='/api/experiments')return new Response(JSON.stringify([{id:'abc',kind:'battle',title:'Recorded failure',created_at:'2026-11-04T12:00:00'}]));
      if(path==='/api/experiments/abc')return new Response(JSON.stringify({id:'abc',kind:'battle',title:'Recorded failure',created_at:'2026-11-04T12:00:00',frames:[],diagnostics:{findings:[finding],metrics:{target_samples:0}}}));
      if(path.startsWith('/api/experiments/abc/prompt'))return new Response('Confirmed exception at seed:42/tick:3/seat:A.');
      throw new Error(`Unexpected ${path}`);
    });
    render(<Diagnostics battle=""/>);
    await waitFor(()=>expect(screen.getByRole('option',{name:/Recorded failure/})).toBeTruthy());
    fireEvent.change(screen.getByRole('combobox',{name:'Experiment history'}),{target:{value:'abc'}});
    await waitFor(()=>expect(screen.getByRole('link',{name:'Export CSV'}).getAttribute('href')).toBe('/api/experiments/abc/export/csv'));
    fireEvent.click(screen.getByRole('button',{name:'Generate improvement prompt'}));
    await waitFor(()=>expect((screen.getByRole('textbox',{name:'Copyable ChatGPT improvement prompt'}) as HTMLTextAreaElement).value).toContain('seed:42/tick:3/seat:A'));
  });
});
