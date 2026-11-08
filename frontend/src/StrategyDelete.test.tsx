// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

vi.mock('./LazyStrategy', () => ({default: () => null, PythonPreview: () => null}));
afterEach(() => {cleanup();vi.restoreAllMocks();});

it('deletes the selected saved benchmark and clears its report selection', async () => {
  vi.spyOn(window,'confirm').mockReturnValue(true);
  const saved={id:'run1',status:'complete'};
  const mock=vi.spyOn(globalThis,'fetch').mockImplementation(async(input,init)=>{
    if(init?.method==='DELETE')return new Response('{"deleted":true}');
    if(String(input)==='/api/benchmarks')return new Response(JSON.stringify([saved]));
    if(String(input)==='/api/benchmarks/run1')return new Response(JSON.stringify(saved));
    return new Response('[]');
  });
  render(<App/>);
  fireEvent.click(screen.getByRole('button',{name:/02 \/ Benchmarks/}));
  await screen.findByRole('option',{name:'run1 · complete'});
  fireEvent.change(screen.getByLabelText('Saved runs'),{target:{value:'run1'}});
  fireEvent.click(await screen.findByRole('button',{name:'Delete benchmark'}));
  await waitFor(()=>expect(screen.queryByRole('option',{name:'run1 · complete'})).toBeNull());
  expect((screen.getByLabelText('Saved runs') as HTMLSelectElement).value).toBe('');
  expect(mock.mock.calls.some(([url,init])=>url==='/api/benchmarks/run1'&&init?.method==='DELETE')).toBe(true);
});

it('confirms deletion, updates selected strategy, and clears comparison', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input) === '/api/versions') return new Response(JSON.stringify([{id:'a',label:'First'}, {id:'b',label:'Second'}]));
    if (init?.method === 'DELETE') return new Response('{"deleted":true}');
    return new Response('[]');
  });
  render(<App/>);
  await waitFor(() => expect((screen.getByLabelText('Strategy version') as HTMLSelectElement).value).toBe('a'));
  fireEvent.click(screen.getByRole('button', {name:/02 \/ Benchmarks/}));
  fireEvent.change(screen.getByLabelText('Compare with'), {target:{value:'b'}});
  fireEvent.click(screen.getByRole('button', {name:/03 \/ Strategy library/}));
  fireEvent.click(screen.getByRole('button', {name:'Delete First'}));
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false);
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole('button', {name:'Delete First'}));
  await waitFor(() => expect(screen.queryByRole('button', {name:'Delete First'})).toBeNull());
  expect((screen.getByLabelText('Strategy version') as HTMLSelectElement).value).toBe('b');
  fireEvent.click(screen.getByRole('button', {name:'Delete Second'}));
  await waitFor(() => expect(screen.getByText('No strategies yet. Upload a Python file to start.')).toBeTruthy());
  expect((screen.getByLabelText('Strategy version') as HTMLSelectElement).value).toBe('');
  fireEvent.click(screen.getByRole('button', {name:/02 \/ Benchmarks/}));
  expect((screen.getByLabelText('Compare with') as HTMLSelectElement).value).toBe('');
});
