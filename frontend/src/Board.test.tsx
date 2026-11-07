// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it} from 'vitest';
import Board from './Board';
import type {Frame} from './types';

afterEach(cleanup);
it('resizes round boards and clamps keyboard coordinates at each boundary',()=>{
  const base:Frame={tick:0,finished:false,abandoned:false,wind:[0,0],traces:[],teams:[],strategy_status:'ready',ranking:[]};
  const {rerender}=render(<Board frame={{...base,config:{map:{rows:36,cols:36},round:'round1',seats:10,groups:2,advance:6,tick_cap:120}}}/>);
  expect(screen.getByRole('img',{name:'36 by 36 battle board'}).getAttribute('viewBox')).toBe('0 0 36 36');
  for(const round of ['round2','final']) {
    rerender(<Board frame={{...base,config:{map:{rows:28,cols:28},round,seats:6,groups:round==='final'?1:2,advance:3,tick_cap:120}}}/>);
    expect(screen.getByRole('img',{name:'28 by 28 battle board'}).getAttribute('viewBox')).toBe('0 0 28 28');
    expect(document.querySelectorAll('.column-labels span')).toHaveLength(28);
    expect(document.querySelectorAll('.row-labels span')).toHaveLength(28);
    const picker=screen.getByRole('button',{name:'Battle grid coordinate picker'});
    for(let i=0;i<40;i++)fireEvent.keyDown(picker,{key:'ArrowRight'});
    for(let i=0;i<40;i++)fireEvent.keyDown(picker,{key:'ArrowDown'});
    expect(screen.getByText('AB28 · [row 27, col 27]')).toBeTruthy();
  }
});
it('renders only recorded booster effects at the selected tick and scales animation duration',()=>{
  const frame:Frame={tick:3,finished:false,abandoned:false,wind:[0,0],traces:[],strategy_status:'ok',ranking:[],teams:[],events:[
    {seat:'A',kind:'flare',ship:'carrier',origin:[1,1],from_cells:[],cells:[],results:[[10,11,'flare']],points:0},
    {seat:'B',kind:'cluster',ship:'carrier',origin:[2,2],from_cells:[],cells:[],results:[[3,4,'hit'],[3,5,'miss']],points:1},
    {seat:'C',kind:'teleport',ship:'carrier',origin:[5,5],from_cells:[[5,5]],cells:[[20,20]],results:[],points:0},
    {seat:'D',kind:'torpedo',ship:'carrier',origin:[8,8],from_cells:[],cells:[],results:[[9,8,'sunk']],sunk_cells:[[9,8],[9,9]],points:4}
  ]};
  const original=JSON.stringify(frame);
  const {container,rerender}=render(<Board frame={frame} speed={4}/>);
  expect(container.querySelector('.board-panel')?.getAttribute('style')).toContain('75ms');
  expect(container.querySelector('.flare-zone')?.getAttribute('x')).toBe('8');
  expect(container.querySelectorAll('.effect-cluster .effect-impact')).toHaveLength(2);
  expect(container.querySelectorAll('.teleport-cell')).toHaveLength(2);
  expect(container.querySelectorAll('.sinking-cell')).toHaveLength(2);
  rerender(<Board frame={{...frame,tick:2,events:[]}} speed={.25}/>);
  expect(container.querySelectorAll('.battle-effects > g')).toHaveLength(0);
  expect(JSON.stringify(frame)).toBe(original);
});
it('shows all selected-team shots as cell scores, including misses',()=>{
  const frame:Frame={tick:1,finished:false,abandoned:false,wind:[0,0],traces:[],strategy_status:'ok',ranking:[],teams:[
    {seat:'A',score:4,wasted:2,eliminated:false,connected:true,ships:[],shots:[[0,0,'miss'],[1,1,'wreck'],[2,2,'hit'],[3,3,'sunk']]},
    {seat:'B',score:0,wasted:1,eliminated:false,connected:true,ships:[{name:'destroyer',cells:[[3,3],[3,4]],holes:[[3,3],[3,4]],sunk:true}],shots:[[4,4,'miss']]}
  ]};
  const {container}=render(<Board frame={frame}/>);
  fireEvent.change(screen.getByRole('combobox',{name:'Trajectory team'}),{target:{value:'A'}});
  for(const title of ['A: miss (0 points)','A: wreck (0 points)','A: hit (1 points)','A: sunk (3 points)']) {
    expect([...container.querySelectorAll('.sea title')].find(node=>node.textContent?.startsWith(title))?.parentElement?.querySelector('text')).toBeTruthy();
  }
  expect([...container.querySelectorAll('.sea text')].map(node=>node.textContent)).toEqual(['0','0','1','3']);
  expect([...container.querySelectorAll('.sea title')].some(node=>node.textContent==='B: miss')).toBe(false);
});

it('retains earlier ticks, combines repeated cells and excludes future shots when seeking',()=>{
  const base:Frame={tick:1,finished:false,abandoned:false,wind:[0,0],traces:[],strategy_status:'ok',ranking:[],teams:[{seat:'A',score:1,wasted:0,eliminated:false,connected:true,ships:[],shots:[[2,2,'hit']]}]};
  const next:Frame={...base,tick:2,teams:[{...base.teams[0],shots:[[2,2,'wreck'],[3,3,'miss']]}]};
  const {container,rerender}=render(<Board frame={next} history={[base,next]}/>);
  expect([...container.querySelectorAll('.sea text')].map(node=>node.textContent)).toEqual(['1','0']);
  expect([...container.querySelectorAll('.sea title')].some(node=>node.textContent?.includes('tick 1')&&node.textContent.includes('tick 2'))).toBe(true);
  rerender(<Board frame={base} history={[base,next]}/>);
  expect([...container.querySelectorAll('.sea text')].map(node=>node.textContent)).toEqual(['1']);
});
