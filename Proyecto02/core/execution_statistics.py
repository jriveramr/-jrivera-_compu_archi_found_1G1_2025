class ExecutionStatistics:
    """
    Mantiene un historial (hasta max_history) de corridas de la simulación,
    registrando ciclos, instrucciones ejecutadas, CPI, tiempo total en ns,
    y número de branch mispredictions.
    """

    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        # Cada entrada: {
        #   'cycles': int,
        #   'instr': int,
        #   'cpi': float,
        #   'time_ns': int,
        #   'mispred': int,
        #   'mispred_rate': float
        # }
        self.history = []

    def add_run(self,
                cycles: int,
                instr_count: int,
                time_ns: int,
                mispredictions: int = 0):
        """
        Añade una nueva corrida al historial.
        :param cycles: Número de ciclos ejecutados
        :param instr_count: Número de instrucciones completadas
        :param time_ns: Tiempo total simulado en nanosegundos
        :param mispredictions: Número de branch mispredictions en la corrida
        """
        cpi = cycles / instr_count if instr_count else float('inf')
        mis_rate = (mispredictions / instr_count
                    if instr_count else float('inf'))
        entry = {
            'cycles':       cycles,
            'instr':        instr_count,
            'cpi':          round(cpi, 2),
            'time_ns':      time_ns,
            'mispred':      mispredictions,
            'mispred_rate': round(mis_rate, 3)
        }
        # Insertar al inicio
        self.history.insert(0, entry)
        # Recortar si excede la historia máxima
        if len(self.history) > self.max_history:
            self.history.pop()

    def display(self):
        """
        Imprime en consola la tabla de estadísticas de las corridas recientes.
        """
        header = (
            f"{'Run':>3} | {'Cycles':>6} | {'Instr':>5} | "
            f"{'CPI':>5} | {'Time(ns)':>8} | "
            f"{'MPreds':>7} | {'Rate':>5}"
        )
        print(header)
        print("-" * len(header))
        for idx, e in enumerate(self.history, start=1):
            print(
                f"{idx:>3} | "
                f"{e['cycles']:>6} | "
                f"{e['instr']:>5} | "
                f"{e['cpi']:>5} | "
                f"{e['time_ns']:>8} | "
                f"{e['mispred']:>7} | "
                f"{e['mispred_rate']:>5}"
            )