"""Local spending guard for explicitly authorized text-only Haiku QA.

This is conservative token accounting, not access to the provider's billing balance.
"""
import json
import threading
from pathlib import Path

MODEL='claude-haiku-4-5-20251001'

class BudgetExceeded(RuntimeError):
    pass

class BudgetGuard:
    def __init__(self, directory, limit_usd=3.5):
        if not 0 < limit_usd <= 3.5:raise ValueError('QA budget must be within $3.50')
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.limit=limit_usd;self.lock=threading.Lock()
        self.spent=0.;self.held=0.;self.calls=0;self.unknown=0
        ledger=self.directory/'budget.json'
        if ledger.exists():
            previous=json.loads(ledger.read_text())
            self.limit=min(self.limit,previous.get('limit_usd',self.limit))
            self.spent=previous['recorded_cost_usd'];self.held=previous['reserved_or_unknown_usd']
            self.calls=previous['provider_attempts'];self.unknown=previous['unknown_usage_calls']

    def _save(self):
        data=dict(limit_usd=self.limit,recorded_cost_usd=round(self.spent,8),reserved_or_unknown_usd=round(self.held,8),
                  committed_max_usd=round(self.spent+self.held,8),provider_attempts=self.calls,
                  unknown_usage_calls=self.unknown,billing_balance='unknown',pricing_source='https://platform.claude.com/docs/en/about-claude/pricing')
        tmp=self.directory/'budget.tmp';tmp.write_text(json.dumps(data,indent=2));tmp.replace(self.directory/'budget.json')

    def reject(self, reason):
        (self.directory/'STOP').write_text(reason+'\n')
        raise BudgetExceeded(reason)

    def send(self, create, client, *args, **kwargs):
        if args or kwargs.get('model')!=MODEL or kwargs.get('tools') or kwargs.get('thinking'):
            self.reject('Unsupported model or billable feature')
        system=kwargs.get('system','');messages=kwargs.get('messages',[])
        if not isinstance(system,str) or not isinstance(messages,list) or any(not isinstance(m.get('content'),str) for m in messages):
            self.reject('Only plain text requests are budgeted')
        tokens=kwargs.get('max_tokens')
        if type(tokens) is not int or not 1<=tokens<=2300:self.reject('Unsupported output token limit')
        # UTF-8 bytes exceed ordinary text token counts. Extra 8192 tokens
        # cover message framing; no images/tools/cache-write features allowed.
        input_ceiling=len(json.dumps(dict(system=system,messages=messages),ensure_ascii=False).encode())+8192
        reserved=(input_ceiling+tokens*5)/1_000_000
        with self.lock:
            if self.spent+self.held+reserved>self.limit:self.reject('Local spending ceiling reached')
            self.held+=reserved;self.calls+=1;self._save()
        try:
            response=create(client,**kwargs)
            usage=response.usage
            cost=(usage.input_tokens+usage.output_tokens*5+
                  (getattr(usage,'cache_creation_input_tokens',0) or 0)*2+
                  (getattr(usage,'cache_read_input_tokens',0) or 0)*.1)/1_000_000
            if cost<0:raise ValueError('Invalid usage')
        except BaseException as error:
            with self.lock:
                self.unknown+=1;self._save()
            # Unknown calls keep their complete reservation. Client/auth errors
            # stop this batch immediately instead of repeatedly trying the key.
            if getattr(error,'status_code',None) in (400,401,402,403):
                (self.directory/'STOP').write_text('Provider rejected request; inspect billing/configuration manually\n')
            raise
        with self.lock:
            self.held=max(0.,self.held-reserved);self.spent+=cost;self._save()
            if cost>reserved or self.spent+self.held>=self.limit:
                (self.directory/'STOP').write_text('Cost ceiling reached or usage exceeded conservative reservation\n')
        return response
