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
        'AUIPC': 0b001110
    }

    def __init__(self,
                 hazard_unit: bool = False,
                 branch_pred: bool = False):
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
    # Si hay que flush–ear (control hazard)…
        if self.flush_next:
            print(f"[Cycle {self.cycle_count}] Flush inserted (control hazard)")
            self.fetch_decode   = None
            self.decode_execute = None
            self.current_stage  = None
            self.flush_next     = False
            self.cycle_count   += 1
            return
        
        # IF→ID→EX→MEM→WB condicionados por hazard_unit
        self.fetch()
        self.decode()
        self.execute()
        self.memory_access()
        self.writeback()
        self.cycle_count += 1

        # Si no, el ciclo normal
        if not self.stall:
            self.fetch()
            self.decode()
            self.execute()
            self.memory_access()
            self.writeback()
        else:
            print(f"[Cycle {self.cycle_count}] Stall inserted")
            self.stall = False

        self.cycle_count += 1

    def fetch(self):
        self.current_stage = 'IF'
        idx = self.pc // 4
        raw = self.memory.load(idx)
        self.fetch_decode = f"{raw:032b}"
        print(f"[Cycle {self.cycle_count}] IF: fetched {self.fetch_decode} from PC={self.pc}")
        self.pc += 4

    def decode(self):
        """
        Etapa ID: Decodifica la instrucción en IF/ID (self.fetch_decode) y
        llena el latch self.decode_execute con un dict de campos.
        También inserta stalls por RAW y aplica forwarding si está habilitado.
        """
        self.current_stage = 'ID'

        # Si no hay instrucción en IF/ID, inyectamos un NOP y salimos
        if self.fetch_decode is None:
            self.decode_execute = None
            return

        b      = self.fetch_decode
        opcode = int(b[0:6], 2)

        # -------- Decodificación --------
        de = {}

        # R-type: ADD, SUB, AND, OR, XOR, SLL, SRL, SLT
        if opcode in (
            self.OPCODES['ADD'], self.OPCODES['SUB'],
            self.OPCODES['AND'], self.OPCODES['OR'],
            self.OPCODES['XOR'], self.OPCODES['SLL'],
            self.OPCODES['SRL'], self.OPCODES['SLT']
        ):
            rd  = int(b[6:11], 2)
            rs1 = int(b[11:16], 2)
            rs2 = int(b[16:21], 2)
            de = {'type':'R',     'opcode':opcode,
                  'rd':rd,        'rs1':rs1,     'rs2':rs2}

        # I-type LW/LOAD
        elif opcode == self.OPCODES['LW']:
            rt  = int(b[6:11], 2)
            rs1 = int(b[11:16], 2)
            imm = self._sign_extend(b[16:], 16)
            de = {'type':'I_LW',  'opcode':opcode,
                  'rt':rt,       'rs1':rs1,     'imm':imm}

        # S-type SW/STORE
        elif opcode == self.OPCODES['SW']:
            imm_hi = int(b[6:11], 2)
            rs1    = int(b[11:16], 2)
            rt     = int(b[16:21], 2)
            imm_lo = int(b[21:],   2)
            imm    = self._sign_extend(f"{imm_hi:05b}{imm_lo:011b}", 16)
            de = {'type':'S_SW',   'opcode':opcode,
                  'rt':rt,        'rs1':rs1,     'imm':imm}

        # B-type BEQ/BNE
        elif opcode in (self.OPCODES['BEQ'], self.OPCODES['BNE']):
            rs1 = int(b[6:11], 2)
            rs2 = int(b[11:16],2)
            imm = self._sign_extend(b[16:], 16)
            de = {'type':'B',      'opcode':opcode,
                  'rs1':rs1,      'rs2':rs2,     'imm':imm}

        # J-type JUMP
        elif opcode == self.OPCODES['JUMP']:
            imm = self._sign_extend(b[6:], 26)
            de = {'type':'J',      'opcode':opcode,
                  'imm':imm}

        # U-type LUI/AUIPC
        elif opcode in (self.OPCODES['LUI'], self.OPCODES['AUIPC']):
            rd  = int(b[6:11], 2)
            imm = int(b[11:],   2) << 11
            de = {'type':'U',      'opcode':opcode,
                  'rd':rd,        'imm':imm}

        else:
            raise ValueError(f"Opcode desconocido en ID: {opcode:06b}")

        # Guardamos la decodificación
        self.decode_execute = de.copy()
        print(f"[Cycle {self.cycle_count}] ID: decoded {self.decode_execute}")

        # ---- Hazard detection + Forwarding ----
        if self.hazard_unit and self.decode_execute:
            # RAW hazard: si rs1 o rs2 coincide con rd de EX/MEM
            rd_ex = self.ex_mem.get('rd')
            if (de['type']=='R' and
                (de['rs1']==rd_ex or de['rs2']==rd_ex)):
                print("  Data hazard → stall next cycle")
                self.stall = True
            else:
                self.stall = False

            # Aplicar forwarding
            self.decode_execute = self.data_forwarding.apply_forwarding(
                self.decode_execute,
                self.registers,
                self.ex_mem,
                self.mem_wb
            )
        else:
            # Sin unidad de riesgos: no stalls, no forwarding
            self.stall = False
            if self.decode_execute is not None:
                self.decode_execute['_forwarded'] = False

        # Mostrar resultado final tras forwarding
        print(f"[Cycle {self.cycle_count}] ID: after hazards/forwarding -> {self.decode_execute}")

    def execute(self):
        self.current_stage = 'EX'
        de = self.decode_execute
        op = de['opcode']
        res = None

        if de['type'] == 'R':
            a = de.get('val1', self.registers.read(de['rs1']))
            b = de.get('val2', self.registers.read(de['rs2']))
            if   op == self.OPCODES['ADD']: res = a + b
            elif op == self.OPCODES['SUB']: res = a - b
            elif op == self.OPCODES['AND']: res = a & b
            elif op == self.OPCODES['OR']:  res = a | b
            elif op == self.OPCODES['XOR']: res = a ^ b
            elif op == self.OPCODES['SLL']: res = (a << b) & 0xFFFFFFFF
            elif op == self.OPCODES['SRL']: res = (a >> b) & 0xFFFFFFFF
            elif op == self.OPCODES['SLT']: res = int(a < b)

        elif de['type'] == 'U':
            res = de['imm']

        elif de['type'] == 'I_LW':
            res = de['imm'] + self.registers.read(de['rs1'])

        elif de['type'] == 'S_SW':
            res = de['imm'] + self.registers.read(de['rs1'])

        elif de['type']=='B':
            a = self.registers.read(de['rs1'])
            b = self.registers.read(de['rs2'])
            taken = ((op==self.OPCODES['BEQ'] and a==b) or
                     (op==self.OPCODES['BNE'] and a!=b))
            # predecimos no-taken:
            prediction = False
            if getattr(self, 'forwarding_prediction', None):
                prediction = self.forwarding_prediction.predict_forwarding(de, self.ex_mem, self.mem_wb)

            # ajuste real del PC
            target = self.pc + de['imm']
            next_pc = self.pc  # this was PC+4 in fetch, pero lo usamos aquí:
            # if taken, target; else implicit fall-through (current PC)
            correct_pc = (target if taken else self.pc)
            if taken and prediction:
                # predije taken y fue taken → OK
                self.pc = target
            elif (not taken) and (not prediction):
                # predije not-taken y no fue taken → OK
                # PC ya vale PC+4 (fetch avanzó antes)
                pass
            else:
                # MISPREDICTION
                self.branch_mispredictions += 1
                # corregimos PC al correcto:
                self.pc = correct_pc
                # en el siguiente ciclo, vamos a flush
                self.flush_next = True

            res = None


        elif de['type'] == 'J':
            self.pc += de['imm']
            res = None

        # guardamos en ex_mem
        self.ex_mem = {
            'type':       de['type'],
            'opcode':     op,
            'rd':         de.get('rd'),
            'rt':         de.get('rt'),
            'alu_result': res,
            'mem_data':   None
        }
        print(f"[Cycle {self.cycle_count}] EX: alu_result = {res}")

        # Preparamos latch EX/MEM
        self.ex_mem = {
            'type':       de['type'],
            'opcode':     op,
            'rd':         de.get('rd'),
            'rt':         de.get('rt'),
            'alu_result': res,
            'mem_data':   None
        }
        print(f"[Cycle {self.cycle_count}] EX: alu_result = {res}")

    def memory_access(self):
        self.current_stage = 'MEM'
        mem = self.ex_mem

        if mem['type'] == 'I_LW':
            addr = mem['alu_result']
            idx  = addr // 4
            data = self.memory.load(idx) if 0 <= idx < len(self.memory.memory) else 0
            mem['mem_data'] = data
            print(f"[Cycle {self.cycle_count}] MEM: loaded {data} from addr {addr}")

        elif mem['type'] == 'S_SW':
            addr = mem['alu_result']
            idx  = addr // 4
            val  = self.registers.read(mem['rt'])
            if 0 <= idx < len(self.memory.memory):
                self.memory.store(idx, val)
            print(f"[Cycle {self.cycle_count}] MEM: stored {val} at addr {addr}")

        self.mem_wb = mem.copy()

    def writeback(self):
        self.current_stage = 'WB'
        wb = self.mem_wb

        # R-type & U-type
        if wb['type'] in ('R', 'U') and wb.get('rd') is not None:
            self.registers.write(wb['rd'], wb['alu_result'])
            print(f"[Cycle {self.cycle_count}] WB: wrote {wb['alu_result']} to x{wb['rd']}")
            self.instr_retired += 1

        # I-type LW
        elif wb['type'] == 'I_LW' and wb.get('rt') is not None:
            self.registers.write(wb['rt'], wb['mem_data'])
            print(f"[Cycle {self.cycle_count}] WB: wrote {wb['mem_data']} to x{wb['rt']}")
            self.instr_retired += 1

        # No writeback para SW, B, J

    @staticmethod
    def _sign_extend(bitstr: str, bits: int) -> int:
        """Sign-extend a bitstring of length `bits` to a Python int."""
        val = int(bitstr, 2)
        if bitstr[0] == '1':
            val -= (1 << bits)
        return val
