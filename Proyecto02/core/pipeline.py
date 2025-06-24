from core.registers import Registers
from core.memory import Memory
from core.pipeline_ade import DataForwarding
from core.pipeline_pred_ade import ForwardingPrediction
from core.execution_statistics import ExecutionStatistics

class Pipeline:
    # Mapeo de opcodes (6 bits)
    OPCODES = {
        'ADD':   0b000000,
        'SUB':   0b000001,
        'AND':   0b000110,
        'OR':    0b000111,
        'XOR':   0b001000,
        'SLL':   0b001001,
        'SRL':   0b001010,
        'SLT':   0b001011,
        'LW':    0b000010,
        'SW':    0b000011,
        'BEQ':   0b000101,
        'BNE':   0b001100,
        'JUMP':  0b000100,
        'LUI':   0b001101,
        'AUIPC': 0b001110,
        'MUL':   0b001111,
        'EBREAK':0b111111   
    }

    def __init__(self, hazard_unit: bool = False, branch_pred: bool = False):
        # Latches del pipeline
        self.fetch_decode   = None
        self.decode_execute = None
        self.ex_mem         = {}
        self.mem_wb         = {}

        # Estado del procesador
        self.pc             = 0
        self.cycle_count    = 0
        self.registers      = Registers()
        self.memory         = Memory()
        self.data_forwarding       = DataForwarding()
        self.forwarding_prediction = ForwardingPrediction()

        self.hazard_unit         = hazard_unit
        self.branch_pred         = branch_pred
        self.data_forwarding     = DataForwarding()      if hazard_unit else None
        self.forwarding_prediction = ForwardingPrediction() if branch_pred else None

        # Flags para GUI y estadísticas
        self.current_stage = None
        self.stall         = False
        self.instr_retired = 0
        self.stats         = ExecutionStatistics()

        self.branch_mispredictions = 0
        self.flush_next = False    # flag para vaciar IF/ID

    def execute_stage(self):
        """
        Realiza un ciclo completo del pipeline:
        - writeback de la etapa anterior
        - memory access
        - execute
        - decode
        - fetch
        """
        # 1) WB
        self.current_stage = 'WB'
        self.writeback()

        # 2) MEM
        self.current_stage = 'MEM'
        self.memory_access()

        # 3) EX
        self.current_stage = 'EX'
        self.execute()

        # 4) ID
        self.current_stage = 'ID'
        self.decode()

        # 5) IF
        self.current_stage = 'IF'
        self.fetch()

        # Contar este ciclo
        self.cycle_count += 1

        # Para debug consola
        print(f"--- End of Cycle {self.cycle_count} (current_stage={self.current_stage}) ---")


    def fetch(self):
        self.current_stage = 'IF'
        # Si pasamos del final de programa, inyectamos NOP
        if self.pc is None or self.pc >= getattr(self, 'program_end', float('inf')):
            self.fetch_decode = None
            return

        idx = self.pc // 4
        # Si idx está fuera del rango de la lista, inyectamos NOP
        if idx < 0 or idx >= len(self.memory.memory):
            self.fetch_decode = None
            return

        raw = self.memory.load(idx)  # :contentReference[oaicite:0]{index=0}
        binstr = f"{raw:032b}"
        self.fetch_decode = binstr
        print(f"[Cycle {self.cycle_count}] IF: fetched {binstr} from PC={self.pc}")

    def decode(self):
        """
        Etapa ID: decodifica la instrucción que vino de IF, construye self.decode_execute
        y luego aplica (si procede) detección de data hazards y forwarding.
        """
        self.current_stage = 'ID'
        raw = self.fetch_decode

        # Si no hay nada (flushed), inyectamos NOP y salimos
        if raw is None:
            self.decode_execute = None
            return

        opcode = int(raw[0:6], 2)

        # Empezamos construyendo el nuevo paquete de ID/EX
        instr = None
        de = {}  # Inicializamos 'de' como un diccionario vacío

        # R-type
        if opcode in (
            self.OPCODES['ADD'], self.OPCODES['SUB'],
            self.OPCODES['AND'], self.OPCODES['OR'],
            self.OPCODES['XOR'], self.OPCODES['SLL'],
            self.OPCODES['SRL'], self.OPCODES['SLT']
        ):
            rd  = int(raw[6:11], 2)
            rs1 = int(raw[11:16], 2)
            rs2 = int(raw[16:21], 2)
            instr = {'type': 'R', 'opcode': opcode, 'rd': rd, 'rs1': rs1, 'rs2': rs2}
            de = instr  # Guardamos el diccionario en 'de'

        # I-type LW
        elif opcode == self.OPCODES['LW']:
            rt  = int(raw[6:11], 2)
            rs1 = int(raw[11:16], 2)
            imm = self._sign_extend(raw[16:], 16)
            instr = {'type': 'I_LW', 'opcode': opcode, 'rt': rt, 'rs1': rs1, 'imm': imm}
            de = instr  # Guardamos el diccionario en 'de'

        # S-type SW
        elif opcode == self.OPCODES['SW']:
            hi5    = int(raw[6:11], 2)
            rs1    = int(raw[11:16], 2)
            rt     = int(raw[16:21], 2)
            lo11   = int(raw[21:], 2)
            imm    = self._sign_extend(f"{hi5:05b}{lo11:011b}", 16)
            instr = {'type': 'S_SW', 'opcode': opcode, 'rt': rt, 'rs1': rs1, 'imm': imm}
            de = instr  # Guardamos el diccionario en 'de'

        # B-type BEQ/BNE
        elif opcode in (self.OPCODES['BEQ'], self.OPCODES['BNE']):
            rs1 = int(raw[6:11], 2)
            rs2 = int(raw[11:16], 2)
            imm = self._sign_extend(raw[16:], 16)
            instr = {'type': 'B', 'opcode': opcode, 'rs1': rs1, 'rs2': rs2, 'imm': imm}
            de = instr  # Guardamos el diccionario en 'de'

        # J-type JUMP
        elif opcode == self.OPCODES['JUMP']:
            imm = self._sign_extend(raw[6:], 26) * 4
            instr = {'type': 'J', 'opcode': opcode, 'imm': imm}
            de = instr  # Guardamos el diccionario en 'de'

        # U-type LUI/AUIPC
        elif opcode in (self.OPCODES['LUI'], self.OPCODES['AUIPC']):
            rd  = int(raw[6:11], 2)
            imm = int(raw[11:], 2) << 11
            instr = {'type': 'U', 'opcode': opcode, 'rd': rd, 'imm': imm}
            de = instr  # Guardamos el diccionario en 'de'

        # --- Manejo de EBREAK ---
        elif opcode == self.OPCODES['EBREAK']:
            print(f"[Cycle {self.cycle_count}] EBREAK: ejecución detenida")
            self.pc = None  # Detenemos la ejecución
            self.ex_mem = None  # Limpiamos el latch EX/MEM para evitar más operaciones

        else:
            raise ValueError(f"Opcode desconocido en ID: {opcode}")

        # Ya tenemos un diccionario válido
        self.decode_execute = de  # Aquí guardamos el diccionario final en self.decode_execute

        # Ahora, si hay unidad de hazards, aplicamos detección y forwarding
        if self.hazard_unit:
            # RAW detection → posible stall
            rd_ex = self.ex_mem.get('rd') if self.ex_mem else None
            if de['type'] == 'R' and (de['rs1'] == rd_ex or de['rs2'] == rd_ex):
                print("  Data hazard → stall next cycle")
                self.stall = True
            else:
                self.stall = False

            # forwarding (DataForwarding debe devolver el mismo dict con campos _forwarded y val1/val2 si aplica)
            self.decode_execute = self.data_forwarding.apply_forwarding(
                self.decode_execute, self.registers, self.ex_mem, self.mem_wb
            )
        else:
            # sin unidad de riesgos: ni stall ni forwarding
            self.stall = False
            self.decode_execute['_forwarded'] = False

        print(f"[Cycle {self.cycle_count}] ID: decoded {self.decode_execute}")


    def execute(self):
        """
        Etapa EX:
        - Calcula el resultado del ALU
        - Gestiona saltos/branch (control hazards → flush + PC)
        - Llena el registro ex_mem para la etapa MEM
        """
        self.current_stage = 'EX'

        # Si hay stall o no hay instrucción: bubble
        if getattr(self, 'stall', False) or self.decode_execute is None:
            self.ex_mem = None
            return

        de = self.decode_execute
        op = de['opcode']
        typ = de['type']

        # Leer operandos (si ya fueron forwardeados, vienen en val1/val2)
        a = de.get('val1', self.registers.read(de.get('rs1', 0)))
        b = de.get('val2', self.registers.read(de.get('rs2', 0)))

        alu_result = None
        branch_taken = False
        target_pc = None

        # --- R-type ---
        if typ == 'R':
            if op == self.OPCODES['ADD']: alu_result = a + b
            elif op == self.OPCODES['SUB']: alu_result = a - b
            elif op == self.OPCODES['AND']: alu_result = a & b
            elif op == self.OPCODES['OR']: alu_result = a | b
            elif op == self.OPCODES['XOR']: alu_result = a ^ b
            elif op == self.OPCODES['SLL']: alu_result = (a << (b & 0x1F)) & 0xFFFFFFFF
            elif op == self.OPCODES['SRL']: alu_result = (a % (1 << 32)) >> (b & 0x1F)
            elif op == self.OPCODES['SLT']: alu_result = 1 if a < b else 0
            elif op == self.OPCODES['MUL']: alu_result = a * b  # Multiplicación

        # --- I-type LW ---
        elif typ == 'I_LW':
            alu_result = a + de['imm']

        # --- S-type SW ---
        elif typ == 'S_SW':
            alu_result = a + de['imm']

        # --- B-type BEQ/BNE ---
        elif typ == 'B':
            if op == self.OPCODES['BEQ']: branch_taken = (a == b)
            elif op == self.OPCODES['BNE']: branch_taken = (a != b)
            target_pc = self.pc + de['imm']

        # --- J-type JUMP ---
        elif typ == 'J':
            branch_taken = True
            imm = self._sign_extend(de['imm'], 26)  # Extiende el valor de 26 bits a 32 bits
            target_pc = self.pc + (imm * 4)  # Multiplica por 4 para obtener el desplazamiento en palabras

        # --- U-type LUI/AUIPC ---
        elif typ == 'U':
            if op == self.OPCODES['LUI']:
                alu_result = de['imm']
            else:  # AUIPC
                alu_result = self.pc + de['imm']

        else:
            raise ValueError(f"Tipo desconocido en EX: {typ}")

        print(f"[Cycle {self.cycle_count}] EX: alu_result = {alu_result}")

        # Preparo el latch EX/MEM
        self.ex_mem = {
            'type': typ,
            'opcode': op,
            'alu_result': alu_result,
            'rd': de.get('rd'),
            'rt': de.get('rt'),
            'rs1': de.get('rs1'),
            'rs2': de.get('rs2'),
            'imm': de.get('imm')
        }

        # Si encontramos un salto o rama, realizamos un flush y actualizamos el PC
        if typ in ('B', 'J'):
            print("Flush inserted (control hazard)")
            self.fetch_decode = None
            self.decode_execute = None
            # Si la rama se toma, actualizamos el PC al target, si no, avanzamos secuencialmente
            self.pc = target_pc if branch_taken else (self.pc + 4)

        else:
            # PC normal avanza 4 bytes
            self.pc += 4



    def memory_access(self):
        """
        Etapa MEM:
        - Para loads: lee de la memoria
        - Para stores: escribe en la memoria
        - Prepara el latch mem_wb para la etapa WB
        """
        self.current_stage = 'MEM'

        # Si no hay nada que procesar (burbuja), propagamos None
        if self.ex_mem is None or 'type' not in self.ex_mem or 'alu_result' not in self.ex_mem:
            self.mem_wb = None
            return

        mem = self.ex_mem
        alu = mem['alu_result']
        typ = mem['type']
        result = None

        # I-type load
        if typ == 'I_LW':
            result = self.memory.load(alu // 4)
            print(f"[Cycle {self.cycle_count}] MEM: loaded {result} from addr {alu}")

        # S-type store
        elif typ == 'S_SW':
            value = self.registers.read(mem['rt'])
            self.memory.store(alu // 4, value)
            print(f"[Cycle {self.cycle_count}] MEM: stored {value} at addr {alu}")

        # Otros tipos no acceden a memoria
        else:
            result = alu  # propagamos el resultado del ALU

        # Preparo EX/MEM → MEM/WB
        self.mem_wb = {
            'type': typ,
            'opcode': mem.get('opcode'),
            'alu_result': alu,
            'load_data': result,
            'rd': mem.get('rd'),
            'rt': mem.get('rt')
        }


    def writeback(self):
        """
        Etapa WB:
        - Para R- y U-types: escribe alu_result en rd
        - Para I_LW: escribe load_data en rt
        - Ignora stores y branches
        """
        self.current_stage = 'WB'

        wb = self.mem_wb
        if wb is None or 'type' not in wb:
            return  

        typ = wb['type']

        # R-type y U-type
        if typ in ('R', 'U') and wb.get('rd') is not None:
            self.registers.write(wb['rd'], wb['alu_result'])
            print(f"[Cycle {self.cycle_count}] WB: wrote {wb['alu_result']} to x{wb['rd']}")
            self.instr_retired += 1

        # I-type load
        elif typ == 'I_LW' and wb.get('rt') is not None:
            self.registers.write(wb['rt'], wb['load_data'])
            print(f"[Cycle {self.cycle_count}] WB: wrote {wb['load_data']} to x{wb['rt']}")
            self.instr_retired += 1

        # Para stores y branches no hay writeback, pero sí contamos retire de la instrucción
        elif typ in ('S_SW', 'B', 'J'):
            # Solo las branch/jump no incrementan instr_retired aquí,
            # asumimos que el retire ocurre en EX para branches/jumps
            if typ == 'S_SW':
                self.instr_retired += 1

        # Incrementar retiros si la instrucción no entró en ninguno de los casos anteriores
        else:
            # Por seguridad, contamos un retire genérico
            self.instr_retired += 1

    @staticmethod
    def _sign_extend(bitstr, bits: int) -> int:
        """Extiende un valor binario de longitud `bits` a un valor con signo."""
        # Si 'bitstr' no es una cadena, lo convertimos a una cadena binaria
        if isinstance(bitstr, int):
            bitstr = format(bitstr, f'{bits}b')  # Convertir el valor entero a una cadena binaria de 'bits' longitud

        # Asegurarse de que 'bitstr' sea una cadena
        if not isinstance(bitstr, str):
            raise TypeError(f"Expected 'bitstr' to be a string, got {type(bitstr)}")

        # Convierte la cadena binaria a un número entero
        val = int(bitstr, 2)

        # Si el bit más significativo es 1 (signo negativo), se extiende
        if bitstr[0] == '1':
            val -= (1 << bits)  # Extiende a negativo

        return val






