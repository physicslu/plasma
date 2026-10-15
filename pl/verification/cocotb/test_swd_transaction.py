"""Wire-only virtual target, independent transaction oracle, deterministic cases."""
import json
import random
from pathlib import Path
import cocotb
from cocotb.triggers import Timer
from swd_reference import DPReference, Request, DPIDR, AP_IDR, POISON, attempts_for
from virtual_swd_target import VirtualSWDTarget


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.targets = {s: VirtualSWDTarget() for s in (1, 2)}
        self.previous_clock = {1: 0, 2: 0}
        self.rise = {1: None, 2: None}
        self.half = {1: 2, 2: 2}
        self.cycles = 0
        self.filter = None
        self.history = []

    def handle(self, site, name):
        return getattr(self.dut, f's{site}_{name}')

    def get(self, site, name):
        return int(self.handle(site, name).value)

    def put(self, site, name, value):
        self.handle(site, name).value = value

    async def tick(self, count=1):
        for _ in range(count):
            self.dut.clk.value = 0
            await Timer(5, units='ns')
            self.dut.clk.value = 1
            await Timer(1, units='ns')
            self.cycles += 1
            for site, target in self.targets.items():
                clock = self.get(site, 'swclk')
                oe, value = self.get(site, 'swdio_oe'), self.get(site, 'swdio_out')
                if clock and not self.previous_clock[site]:
                    self.rise[site] = self.cycles
                    if self.filter:
                        value = self.filter(site, target, value)
                    target.rising(oe, value)
                if not clock and self.previous_clock[site]:
                    forced = not self.get(site,'rst_n') or self.get(site,'cmd_abort') or (
                        self.get(site,'resp_valid') and self.get(site,'resp_status') in (7,8))
                    if not forced:
                        assert self.cycles - self.rise[site] == self.half[site], 'SWCLK high period mismatch'
                assert not (target.drive and oe), f'Site {site} SWDIO contention in {target.state}'
                self.put(site, 'swdio_in', target.value if target.drive else value if oe else 1)
                self.previous_clock[site] = clock
            await Timer(4, units='ns')

    async def setup(self):
        self.dut.clk.value = 0
        defaults = dict(rst_n=0,cmd_abort=0,cmd_valid=0,cmd_op=0,cmd_ap=0,cmd_read=1,
                        cmd_addr=0,cmd_wdata=0,cmd_half_period=2,cmd_turnaround=1,
                        cmd_idle_cycles=8,cmd_max_retries=0,cmd_error_data_phase=0,
                        cmd_timeout_cycles=100000,resp_ready=0,swdio_in=1)
        for site in (1, 2):
            for key,value in defaults.items(): self.put(site,key,value)
        await self.tick(3)
        for site in (1, 2): self.put(site,'rst_n',1)
        await self.tick(2)

    def launch(self, site=1, **kwargs):
        assert self.get(site,'cmd_ready')
        fields = dict(op=0,ap=0,read=1,addr=0,wdata=0,half_period=2,turnaround=1,
                      idle_cycles=8,max_retries=0,error_data_phase=0,timeout_cycles=100000)
        fields.update(kwargs)
        self.half[site] = fields['half_period']
        for name,value in fields.items(): self.put(site,'cmd_'+name,value)
        self.put(site,'cmd_valid',1)
        self.history.append((site, fields))

    def response(self, site=1):
        return {name: self.get(site,'resp_'+name) for name in
                ('status','ack','rdata','data_valid','attempts')}

    async def collect(self, site=1, limit=10000, stall=0):
        for _ in range(limit):
            if self.get(site,'resp_valid'): break
            await self.tick()
        else: raise AssertionError('Response deadline exceeded in test')
        result = self.response(site)
        await self.tick(stall)
        assert result == self.response(site)
        assert self.get(site,'resp_valid') and not self.get(site,'cmd_ready')
        self.put(site,'resp_ready',1)
        await self.tick()
        self.put(site,'resp_ready',0)
        await self.tick()
        return result

    async def command(self, site=1, stall=0, limit=10000, **kwargs):
        self.launch(site,**kwargs)
        await self.tick()
        self.put(site,'cmd_valid',0)
        return await self.collect(site,limit,stall)

    async def connect(self, site=1):
        assert (await self.command(site,op=1))['status'] == 0
        assert self.get(site,'link_state') == 1
        result = await self.command(site)
        assert result == dict(status=0,ack=1,rdata=DPIDR,data_valid=1,attempts=1)
        assert self.get(site,'link_state') == 2

    def save(self, name):
        Path(name+'.json').write_text(json.dumps({'commands':self.history,'targets':{
            s:dict(headers=t.headers,events=t.events,writes=t.writes,wire=t.wire)
            for s,t in self.targets.items()}},indent=2)+'\n')


@cocotb.test()
async def dp_ap_posted_read_and_backpressure(dut):
    b=Bench(dut)
    try:
        await b.setup()
        assert (await b.command())['status'] == 2
        await b.connect()
        assert b.targets[1].wire[-8:] == [(True,0,'header')]*8
        assert b.targets[1].headers == [0xA5]
        assert ('reset_high',64) in b.targets[1].events
        golden=DPReference()
        operations=[(False,False,4,0x50000000),(False,True,4,0),
                    (False,False,8,0),(True,False,0,0x9E3779B9),
                    (True,True,0,0),(False,True,12,0),
                    (False,False,8,0xF0),(True,True,12,0),
                    (False,True,12,0),(False,True,8,0)]
        values=[]
        for ap,read,addr,data in operations:
            request=Request(ap,read,addr)
            expected=golden.read(request) if read else golden.write(request,data)
            wire_start=len(b.targets[1].wire)
            result=await b.command(ap=ap,read=read,addr=addr,wdata=data,stall=5)
            assert len(b.targets[1].wire)-wire_start==54
            assert b.targets[1].wire[-8:]==[(True,0,'header')]*8
            assert result['status']==0 and result['ack']==1 and result['attempts']==1
            assert result['data_valid']==int(read)
            assert result['rdata']==(expected if read else 0)
            assert b.targets[1].headers[-1]==request.header()
            if read: values.append(result['rdata'])
        assert values[1:]==[POISON,0x9E3779B9,POISON,AP_IDR,AP_IDR]
    finally: b.save('dp_ap_posted_read_and_backpressure')


@cocotb.test()
async def ack_errors_retry_and_sticky_recovery(dut):
    b=Bench(dut)
    try:
        await b.setup(); await b.connect()
        t=b.targets[1]
        for acks,retries in [([2,2,1],2),([2,2,2],2),([4],9)]:
            t.ack_script.extend(acks)
            writes=len(t.writes)
            result=await b.command(read=0,addr=8,wdata=0,max_retries=retries)
            n,ack=attempts_for(acks,retries)
            assert result['attempts']==n and result['ack']==ack
            assert result['status']=={1:0,2:3,4:4}[ack]
            assert len(t.writes)-writes==int(ack==1)
        t.ack_script.extend([2]*256)
        result=await b.command(addr=12,max_retries=255,limit=40000)
        assert result['status']==3 and result['attempts']==256
        for ack in (0,3,5,6,7):
            t.ack_script.append(ack)
            result=await b.command(max_retries=255)
            assert result['status']==5 and result['ack']==ack and result['attempts']==1
            assert not result['data_valid'] and b.get(1,'link_state')==0
            assert (await b.command())['status']==2
            await b.connect()
        t.silent=True
        assert (await b.command())['status']==5
        t.silent=False
        await b.connect()
        t.parity_fault=True
        result=await b.command()
        assert result['status']==6 and result['data_valid']==0 and result['rdata']==0
        await b.connect()
        # Write-data parity has no second ACK: transport OK, then WDATAERR.
        def flip_write_parity(site,target,value):
            return value ^ int(site==1 and target.state=='write' and len(target.write_bits)==32)
        b.filter=flip_write_parity
        before=len(t.writes)
        result=await b.command(read=0,addr=8,wdata=0xF0)
        b.filter=None
        assert result['status']==0 and len(t.writes)==before
        assert (await b.command(addr=4))['rdata'] & 128
        assert (await b.command(read=0,addr=8))['status']==4
        assert (await b.command(read=0,addr=0,wdata=8))['status']==0
        assert (await b.command(addr=4))['rdata'] & 128 == 0
    finally: b.save('ack_errors_retry_and_sticky_recovery')


@cocotb.test()
async def turnaround_overrun_data_phase_and_dividers(dut):
    b=Bench(dut)
    try:
        await b.setup(); await b.connect()
        t=b.targets[1]
        for turn in (1,2,3,4):
            t.turnaround=turn # explicit preconfigured target timing fixture
            for half in (2,3,9):
                result=await b.command(turnaround=turn,half_period=half,idle_cycles=33)
                assert result['rdata']==DPIDR and result['status']==0
        t.turnaround=1
        assert (await b.command(read=0,addr=4,wdata=1))['status']==0
        for read in (0,1):
            for ack in (2,4):
                t.ack_script.append(ack)
                before=len(t.writes)
                start=len(t.events)
                result=await b.command(read=read,addr=8,error_data_phase=1)
                assert result['status']==(3 if ack==2 else 4)
                assert len(t.writes)==before and not result['data_valid']
                if read:
                    assert sum(e[0]=='rdata' for e in t.events[start:])==32
                    assert not any(e[2] for e in t.events[start:] if e[0] in ('rdata','rparity'))
                # Explicit ABORT clears sticky overrun before next scenario.
                assert (await b.command(read=0,addr=0,wdata=16,error_data_phase=1))['status']==0
        assert (await b.command(read=0,addr=4,wdata=0,error_data_phase=1))['status']==0
        for half in (65535,):
            result=await b.command(half_period=half,timeout_cycles=100,limit=200)
            assert result['status']==7
        await b.connect()
    finally: b.save('turnaround_overrun_data_phase_and_dividers')


@cocotb.test()
async def config_latching_deadline_abort_and_reset(dut):
    b=Bench(dut)
    try:
        await b.setup(); await b.connect()
        t=b.targets[1]
        for changes in [dict(half_period=0),dict(half_period=1),dict(turnaround=0),
                        dict(turnaround=5),dict(idle_cycles=7),dict(timeout_cycles=0),dict(addr=3)]:
            n=len(t.wire)
            assert (await b.command(**changes))['status']==1
            assert len(t.wire)==n
        b.launch(half_period=3)
        await b.tick(); b.put(1,'cmd_valid',0)
        for name,value in dict(cmd_read=0,cmd_addr=8,cmd_wdata=0xFFFFFFFF,cmd_half_period=50).items():
            b.put(1,name,value)
        result=await b.collect(stall=13)
        assert result['rdata']==DPIDR and result['status']==0
        assert (await b.command(timeout_cycles=1000,stall=1100))['status']==0
        start=b.cycles
        result=await b.command(timeout_cycles=7)
        assert result['status']==7 and b.cycles-start <= 11
        await b.connect()
        # Abort and external reset in request, ACK, data and idle phases.
        for offset in (5,50,90,200,420):
            b.launch(half_period=4)
            await b.tick(); b.put(1,'cmd_valid',0)
            await b.tick(offset)
            assert b.get(1,'busy')
            b.put(1,'cmd_abort',1); await b.tick(); b.put(1,'cmd_abort',0)
            assert (await b.collect())['status']==8
            await b.connect()
        b.launch(); await b.tick(); b.put(1,'cmd_valid',0)
        await b.tick(60)
        b.put(1,'rst_n',0); await b.tick(2); b.put(1,'rst_n',1); await b.tick()
        assert not b.get(1,'resp_valid') and b.get(1,'link_state')==0
        await b.connect()
    finally: b.save('config_latching_deadline_abort_and_reset')


@cocotb.test()
async def independent_sites_and_deterministic_transactions(dut):
    b=Bench(dut)
    try:
        await b.setup(); await b.connect(1); await b.connect(2)
        b.launch(1,half_period=3); b.launch(2,half_period=7)
        await b.tick()
        b.put(1,'cmd_valid',0); b.put(2,'cmd_valid',0)
        await b.tick(20)
        b.put(1,'rst_n',0); await b.tick(2); b.put(1,'rst_n',1)
        result=await b.collect(2)
        assert result['status']==0 and result['rdata']==DPIDR
        await b.connect(1)
        rng=random.Random(0x53574412)
        golden=DPReference()
        for _ in range(24):
            data=rng.getrandbits(32)
            half=rng.choice((2,3,5))
            result=await b.command(ap=1,read=0,wdata=data,half_period=half)
            golden.write(Request(True,False,0),data)
            assert result['status']==0
            expected=golden.read(Request(True,True,0))
            assert (await b.command(ap=1,half_period=half))['rdata']==expected
            expected=golden.read(Request(False,True,12))
            assert (await b.command(addr=12,half_period=half))['rdata']==expected==data
        assert b.targets[2].scratch==0
    finally: b.save('independent_sites_and_deterministic_transactions')


@cocotb.test()
async def malformed_header_and_posted_result_invalidation(dut):
    b=Bench(dut)
    try:
        await b.setup(); await b.connect()
        t=b.targets[1]
        for bit in (5,6,7):
            def corrupt(site,target,value):
                return value ^ int(site==1 and target.state=='header' and len(target.request_bits)==bit)
            b.filter=corrupt
            result=await b.command()
            b.filter=None
            assert result['status']==5 and result['data_valid']==0
            await b.connect()
        assert (await b.command(ap=1,read=0,wdata=0xCAFEBABE))['status']==0
        await b.command(ap=1)
        await b.command(addr=4)  # intervening DP read preserves pending result
        assert (await b.command(addr=12))['rdata']==0xCAFEBABE
        await b.command(ap=1)
        await b.command(read=0,addr=8,wdata=0)  # write invalidates pending result
        assert (await b.command(addr=12))['rdata']==POISON
        # Hold a different command valid during an active read. No acceptance.
        b.launch(half_period=3)
        await b.tick()
        b.put(1,'cmd_op',1)
        while not b.get(1,'resp_valid'):
            assert not b.get(1,'cmd_ready')
            await b.tick()
        snapshot=b.response()
        b.put(1,'cmd_abort',1)
        await b.tick(20)
        assert snapshot==b.response() and not b.get(1,'cmd_ready')
        b.put(1,'cmd_abort',0); b.put(1,'cmd_valid',0)
        assert (await b.collect())['rdata']==DPIDR
    finally: b.save('malformed_header_and_posted_result_invalidation')
