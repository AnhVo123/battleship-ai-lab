from arena_sdk import Bot


class MyBot(Bot):
    def on_state(self, state):
        # self persists across ticks; every battle creates a fresh instance.
        alive = [(index, ship) for index, ship in enumerate(state["you"]["ships"])
                 if not ship["sunk"]]
        index, ship = self.rng.choice(alive)
        return {
            "ship": index,  # local integer adapter; ship["ship"] also works
            "dir": self.rng.uniform(0.0, 360.0),
            "elev": 45.0,
            "power": state["config"]["physics"]["power_max"],
        }
