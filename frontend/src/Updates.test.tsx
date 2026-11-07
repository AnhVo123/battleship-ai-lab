// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import Board, {columnLabel} from './Board';
import Armory from './Armory';
import StrategyWorkbench from './StrategyWorkbench';

vi.mock('@uiw/react-codemirror',()=>({default:({value,onChange,editable}:{value:string;onChange?:(s:string)=>void;editable?:boolean})=><textarea aria-label={editable===false?'Read-only Python source':'Editable Python source'} value={value} readOnly={editable===false} onChange={e=>onChange?.(e.target.value)}/>}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});

describe('requested existing-feature updates',()=>{
  it('labels all columns A–AN, all rows, and retains picked coordinates while zooming',()=>{
    expect([columnLabel(0),columnLabel(25),columnLabel(26),columnLabel(39)]).toEqual(['A','Z','AA','AN']);
    render(<Board frame={null}/>);
    expect(document.querySelectorAll('.column-labels span').length).toBe(36);
    expect(document.querySelectorAll('.row-labels span').length).toBe(36);
    fireEvent.keyDown(screen.getByRole('button',{name:'Battle grid coordinate picker'}),{key:'Enter'});
    expect(screen.getByText('A1 · [row 0, col 0]')).toBeTruthy();
    fireEvent.change(screen.getByRole('slider',{name:'Grid zoom'}),{target:{value:'30'}});
    expect(screen.getByText('A1 · [row 0, col 0]')).toBeTruthy();
    expect(screen.getByText('AJ')).toBeTruthy();
  });
  it('computes quantity costs and shows overspending',()=>{
    function Wrapper(){const [loadout,setLoadout]=useState<Record<string,number>>({});return <Armory round="final" loadout={loadout} onChange={setLoadout} carryover={null} advanced={false} onAdvanced={()=>{}}/>;}
    render(<Wrapper/>);
    fireEvent.change(screen.getByRole('spinbutton',{name:'torpedo quantity'}),{target:{value:'2'}});
    expect(screen.getByRole('status').textContent).toContain('Remaining -4');
  });
  it('pastes, validates and saves a new source version without changing the old one',async()=>{
    const saved=vi.fn().mockResolvedValue(undefined);
    const calls:unknown[]=[];
    vi.spyOn(globalThis,'fetch').mockImplementation(async (input,init)=>{
      const url=String(input);
      if(url==='/api/strategy-template')return new Response('from arena_sdk import Bot');
      if(url==='/api/opponents/medium')return new Response(JSON.stringify({name:'Hunt Target',official:false,algorithm:'Pursue hits',source:'class Opponent: pass',note:'Local source'}));
      if(url==='/api/validate')return new Response(JSON.stringify({valid:true,errors:[]}));
      if(url==='/api/versions'){calls.push(JSON.parse(String(init?.body)));return new Response(JSON.stringify({id:'new',label:'Edited'}));}
      throw new Error(url);
    });
    render(<StrategyWorkbench versions={[]} version="" difficulty="medium" onSaved={saved}/>);
    await waitFor(()=>expect((screen.getByRole('textbox',{name:'Editable Python source'}) as HTMLTextAreaElement).value).toContain('arena_sdk'));
    fireEvent.change(screen.getByRole('textbox',{name:'Editable Python source'}),{target:{value:'edited source'}});
    fireEvent.click(screen.getByRole('button',{name:'Save as new version'}));
    await waitFor(()=>expect(saved).toHaveBeenCalledWith({id:'new',label:'Edited'}));
    expect(calls).toEqual([expect.objectContaining({source:'edited source',filename:'strategy.py'})]);
    expect(screen.getByText(/Custom local implementation/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Read-only preview'}));
    expect(screen.getAllByRole('textbox',{name:'Read-only Python source'}).length).toBe(2);
  });
});
