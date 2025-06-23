class DataForwarding:
    def __init__(self):
        self.forwarding_enabled = True

    def apply_forwarding(self, instr, registers, ex_mem, mem_wb):
        # Prepara valores default
        val1 = None
        val2 = None

        # EX→ID forwarding
        if self.forwarding_enabled and ex_mem:
            if instr.get('rs1') == ex_mem.get('rd'):
                val1 = ex_mem['alu_result']
            if instr.get('rs2') == ex_mem.get('rd'):
                val2 = ex_mem['alu_result']

        # MEM→ID forwarding
        if self.forwarding_enabled and mem_wb:
            if instr.get('rs1') == mem_wb.get('rd'):
                val1 = mem_wb['alu_result'] if mem_wb.get('alu_result') is not None else mem_wb.get('mem_data')
            if instr.get('rs2') == mem_wb.get('rd'):
                val2 = mem_wb['alu_result'] if mem_wb.get('alu_result') is not None else mem_wb.get('mem_data')

        # Guarda flags y valores forwarded
        instr['_forwarded'] = (val1 is not None) or (val2 is not None)
        if val1 is not None: instr['val1'] = val1
        if val2 is not None: instr['val2'] = val2

        return instr
