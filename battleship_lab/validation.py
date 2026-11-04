"""Non-executing checks for the documented strategy import contract."""
import ast
import sys

TEMPLATE = '''from arena_sdk import Bot


class MyBot(Bot):
    def on_state(self, state):
        # Preserve state on self between ticks; a new instance starts each battle.
        alive = [(index, ship) for index, ship in enumerate(state["you"]["ships"])
                 if not ship["sunk"]]
        index, ship = self.rng.choice(alive)
        return {
            "ship": index,  # local integer adapter; ship["ship"] also works
            "dir": self.rng.uniform(0.0, 360.0),
            "elev": 45.0,
            "power": state["config"]["physics"]["power_max"],
        }
'''


def validate_source(content, local_modules=()):
    errors = []
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, UnicodeError) as exc:
        return {"valid":False,"errors":[{"line":getattr(exc,"lineno",None),"message":f"Syntax: {exc}"}]}
    allowed = set(sys.stdlib_module_names) | {'arena_sdk','numpy','scipy','networkx','sortedcontainers'} | set(local_modules)
    bot_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'arena_sdk':
            bot_names.update(item.asname or item.name for item in node.names if item.name == 'Bot')
        names = []
        if isinstance(node,ast.Import):
            names = [item.name.split('.')[0] for item in node.names]
        elif isinstance(node,ast.ImportFrom):
            names = [(node.module or '').split('.')[0]]
        for name in names:
            if name not in allowed or name in ('secrets','importlib'):
                errors.append({"line":node.lineno,"message":f"Import is not permitted by the README: {name or 'relative import'}"})
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('exec','eval','compile','__import__'):
            errors.append({"line":node.lineno,"message":f"The README disallows {node.func.id}()"})
        if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id == 'os' and node.attr == 'urandom':
            errors.append({"line":node.lineno,"message":"The README disallows os.urandom"})
        if isinstance(node,ast.ImportFrom) and node.module == 'os' and any(a.name == 'urandom' for a in node.names):
            errors.append({"line":node.lineno,"message":"The README disallows os.urandom"})
    classes = [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'MyBot']
    if len(classes) != 1 or not any(isinstance(b,ast.Name) and b.id in bot_names for c in classes for b in c.bases):
        errors.append({"line":None,"message":"Define class MyBot(Bot), with Bot imported from arena_sdk"})
    else:
        methods = [n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name == 'on_state']
        if len(methods) != 1:
            errors.append({"line":classes[0].lineno,"message":"Define synchronous on_state(self, state)"})
        else:
            method = methods[0]
            args = method.args.posonlyargs + method.args.args
            if len(args) != 2 or any(default is None for default in method.args.kw_defaults):
                errors.append({"line":method.lineno,"message":"on_state must accept self and state without additional required arguments"})
    return {"valid":not errors,"errors":errors,
            "note":"Static validation does not execute imports or prove runtime behavior. Startup and tick failures are reported separately."}
