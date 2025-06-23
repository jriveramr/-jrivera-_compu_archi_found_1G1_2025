import tkinter as tk
from tkinter import ttk, filedialog

from core.assembler import Assembler
from core.pipeline import Pipeline
from core.registers import Registers
from core.memory import Memory
from core.execution_statistics import ExecutionStatistics

class PipelineView(tk.Tk):
    STAGES = ["IF", "ID", "EX", "MEM", "WB"]
    TIME_PER_STAGE = {'IF':1,'ID':1,'EX':2,'MEM':2,'WB':1}

    def __init__(self):
        super().__init__()
        self.title("Visualización del Pipeline")
        self.geometry("1000x700")
        self.assembler = Assembler()
        self.pipeline  = None
        self.regs      = None
        self.mem       = None
        self.stats     = ExecutionStatistics()
        self._create_widgets()
        self._layout_widgets()

    # ===== Handlers de autoplay (¡ahora al nivel correcto!) =====

    def start_auto(self):
        """Inicia ejecución automática."""
        self.stop_auto()
        self._auto_id = self.after(self.speed_var.get(), self.auto_step)

    def auto_step(self):
        """Avanza un ciclo y reprograma si no ha terminado."""
        self.step()
        if self.pipeline and self.pipeline.pc < getattr(self.pipeline, "program_end", 0):
            self._auto_id = self.after(self.speed_var.get(), self.auto_step)

    def stop_auto(self):
        """Detiene la ejecución automática."""
        if hasattr(self, "_auto_id"):
            self.after_cancel(self._auto_id)

    # ====== Widgets y layout ======

    def _create_widgets(self):

        self.variant_var = tk.IntVar(value=1)
        self.rb_no   = ttk.Radiobutton(self, text="Sin riesgos",    variable=self.variant_var, value=1)
        self.rb_fw   = ttk.Radiobutton(self, text="Con riesgos",    variable=self.variant_var, value=2)
        self.rb_bp   = ttk.Radiobutton(self, text="Predicción",     variable=self.variant_var, value=3)
        self.rb_both = ttk.Radiobutton(self, text="Riesgos+Pred",   variable=self.variant_var, value=4)

        self.speed_var = tk.IntVar(value=500)
        self.lbl_speed = ttk.Label(self, text="Velocidad (ms): 500")
        self.sld_speed = ttk.Scale(self, from_=50, to=1550, variable=self.speed_var,
                                   orient="horizontal",
                                   command=lambda v: self.lbl_speed.config(
                                       text=f"Velocidad (ms): {int(float(v))}"
                                   ))
        self.sld_speed.configure(length=200)

        self.btn_play  = ttk.Button(self, text="▶ Play",  command=self.start_auto)
        self.btn_pause = ttk.Button(self, text="❚❚ Pause", command=self.stop_auto)
        self.btn_load  = ttk.Button(self, text="📂 Cargar Programa", command=self.load_program)

        self.canvas = tk.Canvas(self, width=800, height=120, bg="white", highlightthickness=0)

        self.frm_metrics = ttk.Frame(self)
        self.lbl_metrics = ttk.Label(self.frm_metrics, text="Métricas en vivo:")
        cols = ("m","v")
        self.tree_metrics = ttk.Treeview(self.frm_metrics, columns=cols, show="headings", height=5)
        self.tree_metrics.heading("m", text="Métrica")
        self.tree_metrics.heading("v", text="Valor")
        self.tree_metrics.column("m", width=120, anchor="w")
        self.tree_metrics.column("v", width=80,  anchor="e")

        self.frm_state = ttk.Frame(self)
        self.lbl_regs  = ttk.Label(self.frm_state, text="Reg x0–x7:")
        self.tree_regs = ttk.Treeview(self.frm_state, columns=("val",), show="headings", height=8)
        self.tree_regs.heading("val", text="Valor")
        for i in range(8):
            self.tree_regs.insert("", "end", iid=f"x{i}", values=(0,))
        self.lbl_mem  = ttk.Label(self.frm_state, text="Memoria 0–15:")
        self.tree_mem = ttk.Treeview(self.frm_state, columns=("val",), show="headings", height=8)
        self.tree_mem.heading("val", text="Valor")
        for addr in range(0,16,4):
            self.tree_mem.insert("", "end", iid=str(addr), values=(0,))

        self.btn_step = ttk.Button(self, text="Siguiente Ciclo", command=self.step)

        self.lbl_hist = ttk.Label(self, text="Historial (últimos 10):")
        hist_cols = ("run","cycles","instr","cpi","time_ns","mispred","rate")
        self.tree_hist = ttk.Treeview(self, columns=hist_cols, show="headings", height=5)
        for col,title,w in [
            ("run","Run",40),("cycles","Cycles",60),
            ("instr","Instr",50),("cpi","CPI",50),
            ("time_ns","Time(ns)",70),("mispred","MPreds",60),
            ("rate","Rate",50)
        ]:
            self.tree_hist.heading(col, text=title)
            self.tree_hist.column(col, width=w, anchor="center")

    def _layout_widgets(self):
        pad = {"padx":5,"pady":5}
        # fila 1: radios + slider
        self.rb_no.grid(row=1, column=0, **pad)
        self.rb_fw.grid(row=1, column=1, **pad)
        self.rb_bp.grid(row=1, column=2, **pad)
        self.rb_both.grid(row=1, column=3, **pad)
        self.lbl_speed.grid(row=1, column=4, sticky="e", **pad)
        self.sld_speed.grid(row=1, column=5, sticky="w", **pad)
        # fila 2: botones
        self.btn_play.grid(row=2, column=3, **pad)
        self.btn_pause.grid(row=2, column=4, **pad)
        self.btn_load.grid(row=2, column=5, **pad)
        # fila 3: canvas pipeline
        self.canvas.grid(row=3, column=0, columnspan=6, **pad)
        # fila 4: métricas
        self.frm_metrics.grid(row=4, column=0, columnspan=6, sticky="w", **pad)
        self.lbl_metrics.pack(anchor="w"); self.tree_metrics.pack(fill="x")
        # fila 5: estado regs/mem
        self.frm_state.grid(row=5, column=0, columnspan=6, sticky="nsew", **pad)
        self.lbl_regs.grid(row=0, column=0, sticky="w")
        self.lbl_mem.grid(row=0, column=1, sticky="w")
        self.tree_regs.grid(row=1, column=0, sticky="nsew", padx=(0,20))
        self.tree_mem.grid(row=1, column=1, sticky="nsew")
        self.frm_state.columnconfigure(0, weight=1)
        self.frm_state.columnconfigure(1, weight=1)
        # fila 6: paso a paso
        self.btn_step.grid(row=6, column=0, columnspan=6, **pad)
        # fila 7: historial
        self.lbl_hist.grid(row=7, column=0, columnspan=6, sticky="w", **pad)
        self.tree_hist.grid(row=8, column=0, columnspan=6, sticky="nsew", **pad)

        # expansiones
        for c in range(6):    self.columnconfigure(c, weight=1)
        for r in [0,1,3,5]:   self.rowconfigure(r, weight=0)
        self.rowconfigure(8, weight=1)


    # ====== Pipeline Visual ======

    def _draw_pipeline(self):
        self.canvas.delete("all")
        w,h,gap = 100,50,20
        self.stage_rects = {}
        for i, st in enumerate(self.STAGES):
            x0 = gap + i*(w+gap)
            rect = self.canvas.create_rectangle(x0,10,x0+w,10+h,
                                                fill="lightgrey", outline="black", width=2)
            self.canvas.create_text(x0+w/2, 10+h/2, text=st, font=("Arial",12,"bold"))
            self.stage_rects[st] = rect

    def _highlight_stage(self):
        if not self.pipeline:
            return
        stall = getattr(self.pipeline, "stall", False)
        de    = getattr(self.pipeline, "decode_execute", {}) or {}
        fwd   = bool(de.get("_forwarded", False))
        curr  = getattr(self.pipeline, "current_stage", None)

        for st, rect in self.stage_rects.items():
            color = "lightgrey"
            if stall and st == "ID":
                color = "red"
            elif fwd and st == "EX":
                color = "green"
            elif not stall and not fwd and st == curr:
                color = "orange"
            self.canvas.itemconfig(rect, fill=color)

    def _update_state(self):
        if not self.pipeline:
            return
        for iid in self.tree_metrics.get_children():
            self.tree_metrics.delete(iid)
        rows = [
            ("PC",        self.pipeline.pc),
            ("Ciclos",    self.pipeline.cycle_count),
            ("InstrRet",  self.pipeline.instr_retired),
            ("CPI",       f"{(self.pipeline.cycle_count/self.pipeline.instr_retired):.2f}"
                          if self.pipeline.instr_retired else "0.00"),
            ("Time(ns)",  self.pipeline.cycle_count * sum(self.TIME_PER_STAGE.values()))
        ]
        for m,v in rows:
            self.tree_metrics.insert("", "end", values=(m,v))
        for i in range(8):
            self.tree_regs.set(f"x{i}", "val", self.regs.read(i))
        for addr in range(0,16,4):
            self.tree_mem.set(str(addr), "val", self.mem.load(addr))

    def _refresh_stats(self):
        for iid in self.tree_hist.get_children():
            self.tree_hist.delete(iid)
        for idx, e in enumerate(self.pipeline.stats.history[-10:], start=1):
            self.tree_hist.insert("", "end", values=(
                idx,
                e["cycles"], e["instr"],
                f"{e['cpi']:.2f}", e["time_ns"],
                e.get("mispredictions",0),
                e.get("mispred_rate",0)
            ))

    def load_program(self):
        path = filedialog.askopenfilename(
            title="Seleccionar programa",
            filetypes=[("Text files","*.txt")]
        )
        if not path:
            return
        v      = self.variant_var.get()
        hazard = (v in (2,4))
        pred   = (v in (3,4))
        self.regs     = Registers()
        self.mem      = Memory(size=1024)
        self.pipeline = Pipeline(hazard_unit=hazard, branch_predictor=pred)
        self.pipeline.stats = ExecutionStatistics()
        self.pipeline.registers = self.regs
        self.pipeline.memory    = self.mem
        for t in (self.tree_metrics, self.tree_hist):
            for iid in t.get_children():
                t.delete(iid)
        for i in range(8):
            self.tree_regs.set(f"x{i}", "val", 0)
        for addr in range(0,16,4):
            self.tree_mem.set(str(addr), "val", 0)
        lines = [l.strip() for l in open(path) if l.strip()]
        addr  = 0
        for inst in lines:
            b = self.assembler.assemble(inst)
            w = int(b, 2)
            self.mem.store(addr//4, w)
            addr += 4
        self.pipeline.program_end = addr
        self._draw_pipeline()
        self._update_state()
        self._refresh_stats()

    def step(self):
        if not self.pipeline:
            return
        self.pipeline.execute_stage()
        self._highlight_stage()
        self._update_state()
        if self.pipeline.pc >= getattr(self.pipeline, "program_end", float('inf')):
            c = self.pipeline.cycle_count
            i = self.pipeline.instr_retired
            t = c * sum(self.TIME_PER_STAGE.values())
            m = getattr(self.pipeline, "branch_mispredictions", 0)
            self.pipeline.stats.add_run(
                cycles=c,
                instr_count=i,
                time_ns=t,
                mispredictions=m
            )
            self._refresh_stats()

if __name__ == "__main__":
    PipelineView().mainloop()
