# core/assembler.py

class Assembler:
    """
    Convierte instrucciones RISCV (R, I, S, B, U, J y EBREAK) a su formato binario de 32 bits,
    y permite desensamblar de vuelta a texto.
    """

    def __init__(self):
        # Opcode de 6 bits para cada instrucción
        self.opcodes = {
            'ADD':    0b000000,
            'SUB':    0b000001,
            'MUL':    0b000010,   # soporte MUL
            'AND':    0b000110,
            'OR':     0b000111,
            'XOR':    0b001000,
            'SLL':    0b001001,
            'SRL':    0b001010,
            'SLT':    0b001011,
            'LW':     0b000100,
            'SW':     0b000101,
            'BEQ':    0b000110,
            'BNE':    0b000111,
            'JUMP':   0b001000,
            'LUI':    0b001001,
            'AUIPC':  0b001010,
            'EBREAK': 0b000000,   # lo tratamos como un NOP (all zeros)
        }

        # Para desensamblar: inverso (omitimos aliases aquí)
        self.rev_opcodes = {v: k for k, v in self.opcodes.items()}

        # Alias que acepta tu .txt
        self.aliases = {
            'LOAD':     'LW',
            'STORE':    'SW',
            'MULTIPLY': 'MUL',
            'BRANCH_EQ': 'BEQ',
            'END':      'EBREAK',
        }

    def assemble(self, instr: str) -> str:
        """
        Ensambla una instrucción RISCV de texto a su código binario de 32 bits.
        Líneas vacías o 'end' generan un NOP (32 ceros).
        """
        parts = instr.replace(',', ' ').split()
        if not parts:
            # NOP
            return "0" * 32

        op = parts[0].upper()
        # normaliza alias
        op = self.aliases.get(op, op)

        if op not in self.opcodes:
            raise ValueError(f"Instrucción desconocida: {op}")

        code = self.opcodes[op]

        def reg(x: str) -> int:
            return int(x[1:])

        # R-type: opcode(6) rd(5) rs1(5) rs2(5) padding(11)
        if op in ('ADD','SUB','MUL','AND','OR','XOR','SLL','SRL','SLT'):
            rd, rs1, rs2 = reg(parts[1]), reg(parts[2]), reg(parts[3])
            return (
                f"{code:06b}"
                f"{rd:05b}{rs1:05b}{rs2:05b}"
                f"{0:011b}"
            )

        # I-type (LW)
        if op == 'LW':
            rt = reg(parts[1])
            imm_str, base_str = parts[2].split('(')
            imm  = int(imm_str)
            base = reg(base_str[:-1])
            imm16 = imm & 0xFFFF
            return (
                f"{code:06b}"
                f"{rt:05b}{base:05b}"
                f"{imm16:016b}"
            )

        # S-type (SW)
        if op == 'SW':
            rt = reg(parts[1])
            imm_str, base_str = parts[2].split('(')
            imm  = int(imm_str)
            base = reg(base_str[:-1])
            imm16 = imm & 0xFFFF
            hi5   = (imm16 >> 11) & 0x1F
            lo11  = imm16 & 0x7FF
            return (
                f"{code:06b}"
                f"{hi5:05b}{base:05b}{rt:05b}{lo11:011b}"
            )

        # B-type (BEQ, BNE)
        if op in ('BEQ','BNE'):
            rs1 = reg(parts[1])
            rs2 = reg(parts[2])
            imm = int(parts[3]) & 0xFFFF
            return (
                f"{code:06b}"
                f"{rs1:05b}{rs2:05b}"
                f"{imm:016b}"
            )

        # J-type (JUMP)
        if op == 'JUMP':
            imm26 = int(parts[1]) & ((1 << 26) - 1)
            return f"{code:06b}{imm26:026b}"

        # U-type (LUI, AUIPC)
        if op in ('LUI','AUIPC'):
            rd  = reg(parts[1])
            imm20 = int(parts[2]) & ((1 << 20) - 1)
            return (
                f"{code:06b}"
                f"{rd:05b}"
                f"{imm20:020b}"
            )

        # EBREAK / END → tratamos como NOP
        if op == 'EBREAK':
            return "0" * 32

        # Nunca debería llegar aquí
        raise NotImplementedError(f"Formato no implementado: {op}")

    def disassemble(self, binary: str) -> str:
        """
        Convierte un código binario de 32 bits a su instrucción en texto RISCV.
        """
        if len(binary) != 32 or any(c not in '01' for c in binary):
            raise ValueError("Cadena debe tener exactamente 32 bits")

        opc = int(binary[0:6], 2)
        op  = self.rev_opcodes.get(opc)
        if not op:
            raise ValueError(f"Opcode desconocido: {opc:06b}")

        # R-type
        if op in ('ADD','SUB','MUL','AND','OR','XOR','SLL','SRL','SLT'):
            rd  = int(binary[6:11], 2)
            rs1 = int(binary[11:16], 2)
            rs2 = int(binary[16:21], 2)
            return f"{op} x{rd}, x{rs1}, x{rs2}"

        # I-type LW
        if op == 'LW':
            rt   = int(binary[6:11], 2)
            base = int(binary[11:16], 2)
            imm  = self._sign_extend(binary[16:], 16)
            return f"LW x{rt}, {imm}(x{base})"

        # S-type SW
        if op == 'SW':
            hi5  = int(binary[6:11], 2)
            base = int(binary[11:16], 2)
            rt   = int(binary[16:21], 2)
            lo11 = int(binary[21:],  2)
            imm16 = (hi5 << 11) | lo11
            imm   = self._sign_extend(f"{imm16:016b}", 16)
            return f"SW x{rt}, {imm}(x{base})"

        # B-type
        if op in ('BEQ','BNE'):
            rs1 = int(binary[6:11], 2)
            rs2 = int(binary[11:16], 2)
            imm = self._sign_extend(binary[16:], 16)
            return f"{op} x{rs1}, x{rs2}, {imm}"

        # J-type
        if op == 'JUMP':
            imm = self._sign_extend(binary[6:], 26)
            return f"JUMP {imm}"

        # U-type
        if op in ('LUI','AUIPC'):
            rd  = int(binary[6:11], 2)
            imm = int(binary[11:], 2)
            return f"{op} x{rd}, {imm}"

        # EBREAK
        if op == 'EBREAK':
            return "EBREAK"

        raise NotImplementedError(f"Disassembly no implementado para: {op}")

    @staticmethod
    def _sign_extend(bits: str, width: int) -> int:
        """
        Sign-extends a twos-complement bitstring `bits` of length `width`.
        """
        if bits[0] == '1':
            return int(bits, 2) - (1 << width)
        return int(bits, 2)
