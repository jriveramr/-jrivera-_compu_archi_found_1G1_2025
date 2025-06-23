import time
from core.assembler import Assembler
from core.pipeline import Pipeline
from core.registers import Registers
from core.memory import Memory
from ui.pipeline_view import PipelineView

# Latencias por etapa en nanosegundos
TIME_PER_STAGE_PS = {
    'IF': 200,
    'ID': 150,
    'EX': 500,
    'MEM': 300,
    'WB': 100
}

def load_program(memory: Memory,
                 assembler: Assembler,
                 program: list[str],
                 base_addr: int = 0,
                 pipeline: Pipeline = None):
    """
    Ensambla y carga una lista de instrucciones en memoria (4 B por instrucción),
    y, si se pasa el pipeline, marca pipeline.program_end.
    """
    addr = base_addr
    for instr in program:
        binstr = assembler.assemble(instr)
        word   = int(binstr, 2)
        memory.store(addr // 4, word)
        addr += 4
    if pipeline:
        pipeline.program_end = addr

def print_state(pipeline: Pipeline,
                regs: Registers,
                mem: Memory,
                mem_range: range = range(0, 16, 4)):
    """Muestra PC, registros x0–x7 y un vistazo a memoria."""
    print(f"  PC = {pipeline.pc}")
    print("  Registros:", [regs.read(i) for i in range(8)])
    print("  Memoria:")
    for addr in mem_range:
        print(f"    [{addr:03}] = {mem.load(addr // 4)}")
    print()

def simulation_mode(pipeline: Pipeline,
                    regs: Registers,
                    mem: Memory,
                    max_cycles: int = 10,
                    delay: float = 1.0):
    """Ejecuta el pipeline por max_cycles ciclos, con retardo."""
    for cycle in range(1, max_cycles + 1):
        print(f"=== Ciclo {cycle} ===")
        pipeline.execute_stage()
        print_state(pipeline, regs, mem)
        time.sleep(delay)

def step_by_step_mode(pipeline: Pipeline,
                      regs: Registers,
                      mem: Memory):
    """Permite avanzar ciclo a ciclo con Enter."""
    cycle = 0
    while True:
        cmd = input("Pulse Enter para un ciclo (o 'q' para salir): ").strip().lower()
        if cmd == 'q':
            break
        cycle += 1
        print(f"=== Ciclo {cycle} ===")
        pipeline.execute_stage()
        print_state(pipeline, regs, mem)

def run_to_end_mode(pipeline: Pipeline,
                    regs: Registers,
                    mem: Memory,
                    max_cycles: int = 1000):
    """Corre hasta pipeline.program_end o max_cycles."""
    for cycle in range(1, max_cycles + 1):
        if hasattr(pipeline, 'program_end') and pipeline.pc >= pipeline.program_end:
            print("=== Fin de programa alcanzado ===")
            break
        print(f"=== Ciclo {cycle} ===")
        pipeline.execute_stage()
        print_state(pipeline, regs, mem)

def record_stats(pipeline: Pipeline):
    """Calcula tiempo simulado y registra la corrida en pipeline.stats."""
    cycles     = pipeline.cycle_count
    instrs     = getattr(pipeline, 'instr_retired', 0)
    # Tiempo en ps
    total_ps   = cycles * sum(TIME_PER_STAGE_PS.values())
    # Convertimos a ns para la tabla
    total_ns   = total_ps / 1000.0
    pipeline.stats.add_run(
        cycles=cycles,
        instr_count=instrs,
        time_ns=total_ns,
        mispredictions=getattr(pipeline, 'branch_mispredictions', 0)
    )

def main():


        # 1) Inicialización
    assembler = Assembler()
    regs      = Registers()
    mem       = Memory(size=1024)
    pipeline  = Pipeline()

    # Asegurarnos de que el pipeline use nuestras instancias
    pipeline.registers = regs
    pipeline.memory    = mem


    # 2) Programa de prueba (puedes reemplazarlo tras pulsar "Cargar Programa")
    program = [
        "LUI x1, 1000",
        "AUIPC x2, 2000",
        "ADD x3, x1, x2",
        "SUB x4, x3, x1",
        "AND x5, x3, x4",
        "OR x6, x5, x2",
        "XOR x7, x6, x1",
        "SLL x8, x7, x1",
        "SRL x9, x8, x2",
        "SLT x10, x9, x3",
        "LW x11, 0(x1)",
        "SW x11, 4(x1)",
        "BEQ x3, x4, 8",
        "BNE x5, x6, 12",
        "JUMP 16"
    ]

    # 3) Cargar programa y marcar fin
    load_program(mem, assembler, program, base_addr=0, pipeline=pipeline)

    # 4) Menú de modos de ejecución
    print("\nBienvenido a la simulación del procesador")
    print("1: Simulación automática (10 ciclos)")
    print("2: Ejecución paso a paso")
    print("3: Ejecución hasta fin de programa")
    print("4: Visualización gráfica del pipeline")
    mode = input("Seleccione modo (1/2/3/4): ").strip()

    if mode == '1':
        simulation_mode(pipeline, regs, mem, max_cycles=10, delay=1.0)
    elif mode == '2':
        step_by_step_mode(pipeline, regs, mem)
    elif mode == '3':
        run_to_end_mode(pipeline, regs, mem, max_cycles=1000)
    elif mode == '4':
        # Levanta la GUI con carga dinámica y flushing visual
        view = PipelineView(pipeline, regs, mem)
        view.mainloop()
    else:
        print("Opción no válida. Saliendo.")
        return

    # 5) Registrar y mostrar métricas
    record_stats(pipeline)
    print("\n=== Estadísticas de ejecuciones recientes ===")
    pipeline.stats.display()


if __name__ == "__main__":
    main()
