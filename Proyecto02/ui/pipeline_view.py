import tkinter as tk
from tkinter import ttk, filedialog
from core.assembler import Assembler
from core.pipeline import Pipeline
from core.registers import Registers
from core.memory import Memory
from core.pipeline_ade import DataForwarding
from core.pipeline_pred_ade import ForwardingPrediction
from core.execution_statistics import ExecutionStatistics

class PipelineView(tk.Tk):
    STAGES = ["IF", "ID", "EX", "MEM", "WB"]
    TIME_PER_STAGE = {'IF':1,'ID':1,'EX':2,'MEM':2,'WB':1}

    def __init__(self, pipeline: Pipeline, regs: Registers, mem: Memory):
        super().__init__()
        self.pipeline = pipeline
        self.regs     = regs
        self.mem      = mem
        self.title("Visualización del Pipeline")
        self.geometry("1200x700")

        self.assembler = Assembler()

        # ─── Crear paneles ───────────────────────────
        self.top_frame    = ttk.Frame(self); self.top_frame.pack(fill="x", pady=5)
        self.middle_frame = ttk.Frame(self); self.middle_frame.pack(fill="both", expand=True, pady=5)
        self.bottom_frame = ttk.Frame(self); self.bottom_frame.pack(fill="x", pady=5)

        self._create_top_controls()
        self._create_middle_panel()
        self._create_bottom_history()

        self._draw_pipeline()
        self._update_state()
        self._refresh_history()
        self.apply_variant()

    def apply_variant(self):
            v = self.variant.get()
            # unidad de riesgos = forwarding+stalls si v in {2,4}
            self.pipeline.hazard_unit = (v in (2,4))
            self.pipeline.data_forwarding = DataForwarding() if v in (2,4) else None
            # predicción de saltos con flush si v in {3,4}
            self.pipeline.branch_predictor = ForwardingPrediction() if v in (3,4) else None
            # para que pipeline siempre tenga el atributo (evita None)
            if not hasattr(self.pipeline, 'forwarding_prediction'):
                self.pipeline.forwarding_prediction = self.pipeline.branch_predictor

    # ─── PANEL SUPERIOR: controles y slider ──────────
    def _create_top_controls(self):
        # Variante de pipeline
        ttk.Label(self.top_frame, text="Variante de pipeline:").pack(side="left", padx=(10,0))
        self.variant = tk.IntVar(value=4)

        for val, txt in [(1,"Sin riesgos"),(2,"Con riesgos"),(3,"Predicción"),(4,"Riesgos+Pred")]:
            ttk.Radiobutton(self.top_frame, text=txt, variable=self.variant, value=val).pack(side="left", padx=5)

        # Slider velocidad
        ttk.Label(self.top_frame, text="Velocidad (ms):").pack(side="left", padx=(20,0))
        self.speed_scale = tk.Scale(
            self.top_frame, from_=50, to=2000, resolution=50,
            orient="horizontal", length=200, tickinterval=500
        )
        self.speed_scale.set(500)
        self.speed_scale.pack(side="left", padx=5)

        # Botones Load / Play / Pause
        self.btn_load  = ttk.Button(self.top_frame, text="Cargar Programa", command=self.load_program)
        self.btn_load.pack(side="left", padx=10)
        self.is_playing = False
        self.btn_play  = ttk.Button(self.top_frame, text="▶ Play",  command=self.toggle_play)
        self.btn_pause = ttk.Button(self.top_frame, text="❚❚ Pause", command=self.toggle_play, state="disabled")
        self.btn_play.pack(side="left", padx=5)
        self.btn_pause.pack(side="left")

    # ─── PANEL MEDIO: canvas + métricas live ────────
    def _create_middle_panel(self):
        # izquierda: canvas pipeline
        self.canvas = tk.Canvas(self.middle_frame, width=600, height=120, bg="white")
        self.canvas.grid(row=0, column=0, padx=10, pady=5, sticky="nw")

        # derecha: Treeview de métricas
        metrics_frame = ttk.Frame(self.middle_frame)
        metrics_frame.grid(row=0, column=1, padx=10, sticky="ne")
        ttk.Label(metrics_frame, text="Métricas en vivo:", font=("Arial",12,"underline")).pack(anchor="w")
        cols = ("metric","value")
        self.live_tree = ttk.Treeview(metrics_frame, columns=cols, show="headings", height=5)
        self.live_tree.heading("metric", text="Métrica")
        self.live_tree.heading("value",  text="Valor")
        self.live_tree.column("metric", width=100, anchor="w")
        self.live_tree.column("value",  width=80, anchor="e")
        for m in ["PC","Ciclos","Instr Ret.","CPI","Time(ns)"]:
            self.live_tree.insert("", "end", iid=m, values=(m,"0"))
        self.live_tree.pack()

    # ─── PANEL INFERIOR: historial ───────────────────
    def _create_bottom_history(self):
        ttk.Label(self.bottom_frame, text="Historial (últimos 10):").pack(anchor="w", padx=10)
        cols = ("run","cycles","instr","cpi","time_ns","mispred","rate")
        self.stats_tree = ttk.Treeview(self.bottom_frame, columns=cols, show="headings", height=6)
        for col,title,w in [
            ("run","Run",40),("cycles","Cycles",60),("instr","Instr",50),
            ("cpi","CPI",50),("time_ns","Time(ns)",70),
            ("mispred","MPreds",60),("rate","Rate",50)
        ]:
            self.stats_tree.heading(col, text=title)
            self.stats_tree.column(col, width=w, anchor="center")
        self.stats_tree.pack(fill="x", padx=10, pady=5)

    # ─── Dibuja y refresca ───────────────────────────
    def _draw_pipeline(self):
        self.rects = {}
        w,h,gap = 100,50,20
        for i, stage in enumerate(self.STAGES):
            x0 = gap + i*(w+gap); y0 = 10
            rect = self.canvas.create_rectangle(x0,y0,x0+w,y0+h, fill="lightgrey", outline="black", width=2)
            self.canvas.create_text(x0+w/2, y0+h/2, text=stage, font=("Arial",12,"bold"))
            self.rects[stage] = rect

    def _highlight_stage(self):
        stall   = getattr(self.pipeline, "stall", False)
        de      = getattr(self.pipeline, "decode_execute", {}) or {}
        fwd     = bool(de.get("_forwarded", False))
        current = getattr(self.pipeline, "current_stage", None)

        for stage, rect in self.rects.items():
            color = "lightgrey"
            if stall   and stage=="ID":  color="red"
            elif fwd   and stage=="EX":  color="green"
            elif (not stall and not fwd) and stage==current: color="orange"
            self.canvas.itemconfig(rect, fill=color)

    def _update_state(self):
        # live pipeline & regs/mem updated elsewhere...
        # ─── Actualiza métricas “en vivo” ─────────────
        pc    = self.pipeline.pc
        cyc   = self.pipeline.cycle_count
        instr = getattr(self.pipeline, "instr_retired", 0)
        cpi   = (cyc/instr) if instr>0 else 0.0
        t_ns  = cyc * sum(self.TIME_PER_STAGE.values())
        for key,val in [("PC",pc),("Ciclos",cyc),("Instr Ret.",instr),
                        ("CPI",f"{cpi:.2f}"),("Time(ns)",f"{t_ns}")]:
            self.live_tree.set(key, "value", val)

    def _refresh_history(self):
        for r in self.stats_tree.get_children(): self.stats_tree.delete(r)
        for idx, e in enumerate(self.pipeline.stats.history[-10:], start=1):
            self.stats_tree.insert("", "end", values=(
                idx, e["cycles"], e["instr"], e["cpi"],
                e["time_ns"], e.get("mispred",0), e.get("mispred_rate",0)
            ))

    # ─── Carga / Step / Auto ────────────────────────
    def load_program(self):
        # limpia estado...
        path = filedialog.askopenfilename(...)
        # similar a tu load, luego:
        self._update_state()
        self._highlight_stage()
        self._refresh_history()
        self.apply_variant()

    def toggle_play(self):
        if not self.is_playing:
            self.is_playing = True
            self.btn_play.config(state="disabled"); self.btn_pause.config(state="normal")
            self._auto_step()
        else:
            self.is_playing = False
            self.btn_play.config(state="normal");  self.btn_pause.config(state="disabled")

    def _auto_step(self):
        if not self.is_playing: return
        self.step()
        delay = self.speed_scale.get()
        self.after(int(delay), self._auto_step)

    def step(self):
        self.pipeline.execute_stage()
        self._highlight_stage()
        self._update_state()
        if hasattr(self.pipeline, "program_end") and self.pipeline.pc>=self.pipeline.program_end:
            # registrar stats
            c= self.pipeline.cycle_count
            i= self.pipeline.instr_retired
            t= c*sum(self.TIME_PER_STAGE.values())
            m= getattr(self.pipeline, "branch_mispredictions",0)
            self.pipeline.stats.add_run(cycles=c,instr_count=i,time_ns=t,mispredictions=m)
        self._refresh_history()

