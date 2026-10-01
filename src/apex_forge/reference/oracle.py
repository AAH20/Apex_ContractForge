"""Independent dictionary model of the declared core transition system."""
from dataclasses import dataclass, field

@dataclass
class Oracle:
    instruments: int=8
    max_pending: int=16
    window_cycles: int=64
    hold: bool=True
    epoch: int=0
    expected: int=1
    next_id: int=1
    exposure: int=0
    threshold: int=100
    order_qty: int=1
    max_exposure: int=16
    rate_limit: int=16
    window: int=0
    rate: int=0
    pending: dict=field(default_factory=dict)
    book: dict=field(default_factory=dict)
    output: tuple | None=None
    status: int=0

    def step(self, event: dict) -> dict:
        ready=not self.hold and not event['terminal_valid'] and (self.output is None or event['out_ready']) and not event['recover']
        self.status=0
        if self.output is not None and event['out_ready']:
            self.pending[self.output[0]]['sent']=True
            self.output=None
        self.window+=1
        if self.window==self.window_cycles:
            self.window=0;self.rate=0
        if event['recover']:
            if self.hold and self.exposure==0 and self.output is None and event['epoch']>self.epoch and event['qty']>0 and event['limit']>0 and event['rate_limit']>0 and event['seq']>0:
                self.hold=False;self.epoch=event['epoch'];self.expected=event['seq'];self.threshold=event['price'];self.order_qty=event['qty'];self.max_exposure=event['limit'];self.rate_limit=event['rate_limit'];self.rate=0;self.window=0
        elif event['terminal_valid']:
            order=self.pending.get(event['terminal_id'])
            if order and order['sent']:
                self.exposure-=order['qty'];del self.pending[event['terminal_id']];self.status=8
            else:self.status=9
        elif event['valid'] and ready:
            if not event['frame_ok'] or event['epoch']!=self.epoch or event['instrument']>=self.instruments or event['price']==0 or event['qty']==0:
                self.hold=True;self.status=1
            elif event['seq']<self.expected:self.status=2
            elif event['seq']!=self.expected or self.expected==(1<<64)-1:
                self.hold=True;self.status=3
            else:
                self.expected+=1;self.book[event['instrument']]=event['price']
                if event['price']>self.threshold or event['qty']<self.order_qty:self.status=6
                elif len(self.pending)>=self.max_pending or self.exposure+self.order_qty>self.max_exposure or self.rate>=self.rate_limit:self.status=4
                elif self.next_id==(1<<64)-1:self.hold=True;self.status=7
                else:
                    self.output=(self.next_id,event['instrument'],event['price'],self.order_qty)
                    self.pending[self.next_id]={'qty':self.order_qty,'sent':False}
                    self.next_id+=1;self.exposure+=self.order_qty;self.rate+=1;self.status=5
        if self.output is None: order=(0,0,0,0)
        else:order=self.output
        return {'ready':int(ready),'out_valid':int(self.output is not None),'order':order,'hold':int(self.hold),'exposure':self.exposure,'expected':self.expected,'status':self.status}


def stimulus(**updates):
    result=dict(recover=0,terminal_valid=0,terminal_id=0,valid=0,frame_ok=1,seq=1,instrument=0,price=100,qty=1,epoch=1,limit=16,rate_limit=16,out_ready=1)
    result.update(updates)
    return result
