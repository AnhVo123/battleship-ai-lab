import { lazy, Suspense } from 'react';
import type { ComponentProps } from 'react';

const Workbench = lazy(() => import('./StrategyWorkbench'));
const Preview = lazy(() => import('./StrategyWorkbench').then(module => ({default: module.PythonPreview})));

export function PythonPreview({source}:{source:string}) {
  return <Suspense fallback={<p>Loading source viewer…</p>}><Preview source={source}/></Suspense>;
}

export default function StrategyWorkbench(props:ComponentProps<typeof Workbench>) {
  return <Suspense fallback={<p>Loading strategy editor…</p>}><Workbench {...props}/></Suspense>;
}
