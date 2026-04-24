import asyncio
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console
from rich.text import Text

console = Console()

class UI:
    def __init__(self, engine):
        self.engine = engine
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=8)
        )
        self.layout["main"].split_row(
            Layout(name="market"),
            Layout(name="inventory")
        )

    def generate_header(self):
        title = f"🎯 TARGET WINDOW: {self.engine.current_window_slug} | ⏳ T-MINUS: {self.engine.t_minus}s"
        color = "green" if 20 <= self.engine.t_minus <= 300 else "red"
        return Panel(Text(title, style=f"bold {color}", justify="center"))

    def generate_market(self):
        up_color = "green" if self.engine.last_up_ask <= 0.40 else "yellow"
        down_color = "green" if self.engine.last_down_ask <= 0.40 else "yellow"
        
        up_status = "SNIPING ZONE!" if self.engine.last_up_ask <= 0.40 and self.engine.last_up_ask > 0 else "WAITING"
        down_status = "SNIPING ZONE!" if self.engine.last_down_ask <= 0.40 and self.engine.last_down_ask > 0 else "WAITING"
        
        spread = 0.0
        if self.engine.last_up_ask > 0 and self.engine.last_down_ask > 0:
            # Approximated spread for display
            spread = round((1.0 - (self.engine.last_up_ask + self.engine.last_down_ask)) * 100, 2)
            
        content = f"📈 UP ASK   : [{up_color}]{self.engine.last_up_ask:.2f} ({up_status})[/{up_color}]\n"
        content += f"📉 DOWN ASK : [{down_color}]{self.engine.last_down_ask:.2f} ({down_status})[/{down_color}]\n\n"
        content += f"📊 SPREAD   : {spread}%"
        return Panel(content, title="LIVE MARKET (TARGET: ≤ 0.40)")

    def generate_inventory(self):
        up_box = "[X]" if self.engine.has_up else "[ ]"
        down_box = "[X]" if self.engine.has_down else "[ ]"
        total_cost = self.engine.up_invested_usd + self.engine.down_invested_usd
        
        content = f"{up_box} UP FILLED\n"
        content += f"{down_box} DOWN FILLED\n\n"
        content += f"💰 COST: ${total_cost:.2f}"
        return Panel(content, title="INVENTORY")
        
    def generate_footer(self):
        logs = "\n".join(self.engine.executions)
        return Panel(logs, title="EXECUTIONS")

    def update_layout(self):
        self.layout["header"].update(self.generate_header())
        self.layout["market"].update(self.generate_market())
        self.layout["inventory"].update(self.generate_inventory())
        self.layout["footer"].update(self.generate_footer())

    async def render_ui(self):
        with Live(self.layout, refresh_per_second=2, screen=True) as live:
            while True:
                self.update_layout()
                await asyncio.sleep(0.5)

