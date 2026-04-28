import asyncio
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console
from rich.text import Text
from .config import config

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
        color = "green" if self.engine.t_minus > config.GOLDEN_WINDOW_END_SEC else ("red blink" if self.engine.panic_mode else "yellow")
        
        if not self.engine.window_active:
            title += " [SKIPPED]"
            color = "dim"
            
        return Panel(Text(title, style=f"bold {color}", justify="center"))

    def generate_market(self):
        up_color = "green" if 0 < self.engine.last_up_ask <= self.engine.dynamic_target else "yellow"
        down_color = "green" if 0 < self.engine.last_down_ask <= self.engine.dynamic_target else "yellow"
        
        up_status = "TARGET ZN!" if 0 < self.engine.last_up_ask <= self.engine.dynamic_target else "WAITING"
        down_status = "TARGET ZN!" if 0 < self.engine.last_down_ask <= self.engine.dynamic_target else "WAITING"
        
        spread = 0.0
        if self.engine.last_up_ask > 0 and self.engine.last_down_ask > 0:
            spread = round((1.0 - (self.engine.last_up_ask + self.engine.last_down_ask)) * 100, 2)
            
        content = f"📈 UP ASK   : [{up_color}]{self.engine.last_up_ask:.2f} ({up_status})[/{up_color}]\n"
        content += f"   UP BID   : {self.engine.last_up_bid:.2f}\n"
        content += f"📉 DOWN ASK : [{down_color}]{self.engine.last_down_ask:.2f} ({down_status})[/{down_color}]\n"
        content += f"   DOWN BID : {self.engine.last_down_bid:.2f}\n\n"
        content += f"🎯 DYNAMIC TARGET : ≤ {self.engine.dynamic_target:.2f}\n"
        content += f"📊 SPREAD   : {spread}%"
        return Panel(content, title="LIVE MARKET")

    def generate_inventory(self):
        up_box = "[X]" if self.engine.has_up else "[ ]"
        down_box = "[X]" if self.engine.has_down else "[ ]"
        
        content = f"{up_box} UP FILLED\n"
        content += f"{down_box} DOWN FILLED\n\n"
        
        status_color = "white"
        if self.engine.dead_zone_active:
            status = "💤 DEAD ZONE (Engine Sleeping)"
            status_color = "bold blue"
        elif not self.engine.window_active:
            status = "SKIPPED (NO ENTRY FOUND)"
            status_color = "dim"
        elif self.engine.panic_mode:
            status = "🚨 PANIC EXIT EXECUTED 🚨"
            status_color = "bold red blink"
        elif self.engine.has_up and self.engine.has_down:
            status = "✅ POSITION COMPLETE (HEDGED)"
            status_color = "bold green"
        elif self.engine.has_up or self.engine.has_down:
            status = "⚠️ HUNTING LEG 2"
            status_color = "bold yellow"
        else:
            status = "READY TO SNIPE"
            
        content += f"[{status_color}]{status}[/{status_color}]"
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
        with Live(self.layout, refresh_per_second=4, screen=True) as live:
            while True:
                self.update_layout()
                await asyncio.sleep(0.25)

