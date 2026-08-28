# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import typing

@allow_storage
@dataclass
class FlightPolicy:
    policy_id: str
    owner: Address
    flight_number: str
    departure_date: str
    source_url: str
    payout_amount: str
    status: str
    decision: i8
    summary: str
    evidence: str

class FlightGuard(gl.Contract):
    policies: TreeMap[str, FlightPolicy]
    next_policy_id: u256

    def __init__(self):
        self.next_policy_id = 1

    @gl.public.write
    def create_policy(self, flight_number: str, departure_date: str, source_url: str, payout_amount: str) -> str:
        flight_number = flight_number.strip().upper()
        departure_date = departure_date.strip()
        source_url = source_url.strip()
        payout_amount = payout_amount.strip()
        if not flight_number: raise gl.vm.UserError("Flight number is required.")
        if not departure_date: raise gl.vm.UserError("Departure date is required.")
        if not source_url.startswith("https://"): raise gl.vm.UserError("Source URL must start with https://")
        if not payout_amount: raise gl.vm.UserError("Protection amount is required.")
        policy_id = str(self.next_policy_id)
        self.policies[policy_id] = FlightPolicy(policy_id, gl.message.sender_address, flight_number, departure_date, source_url, payout_amount, "ACTIVE", -1, "Waiting for flight evaluation.", "")
        self.next_policy_id += 1
        return policy_id

    @gl.public.write
    def evaluate_policy(self, policy_id: str) -> typing.Any:
        if policy_id not in self.policies: raise gl.vm.UserError("Policy does not exist.")
        policy = gl.storage.copy_to_memory(self.policies[policy_id])
        if policy.status == "RESOLVED": raise gl.vm.UserError("This policy has already been resolved.")
        flight_number, departure_date, source_url = policy.flight_number, policy.departure_date, policy.source_url

        def leader_fn():
            web_data = gl.nondet.web.render(source_url, mode="text", wait_after_loaded="3s")
            prompt = f"""
You are a flight-disruption evidence evaluator.
TARGET FLIGHT: {flight_number}
DEPARTURE DATE: {departure_date}
SOURCE URL: {source_url}
SOURCE CONTENT:
{web_data}

Use ONLY the supplied source. The evidence must clearly refer to the target flight and date.
1 = cancelled OR delayed 120 minutes or more.
0 = on time OR delayed less than 120 minutes.
-1 = insufficient, contradictory, stale, or not-yet-determinable evidence.
Never guess or use unrelated flights/dates.
Return JSON only:
{{"decision":1,"status":"Cancelled","summary":"short evidence-based explanation","evidence":"short factual excerpt"}}
"""
            result = gl.nondet.exec_prompt(prompt, response_format="json")
            if not isinstance(result, dict): raise gl.vm.UserError("LLM did not return an object.")
            decision, status, summary, evidence = result.get("decision"), result.get("status"), result.get("summary"), result.get("evidence")
            if decision not in [1, 0, -1] or not isinstance(status, str) or not isinstance(summary, str) or not isinstance(evidence, str):
                raise gl.vm.UserError("Invalid evaluation result.")
            return {"decision": decision, "status": status[:120], "summary": summary[:500], "evidence": evidence[:800]}

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return): return False
            try: own = leader_fn()
            except Exception: return False
            leader = leader_result.calldata
            return isinstance(leader, dict) and own.get("decision") == leader.get("decision") and own.get("decision") in [1, 0, -1]

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        decision = result["decision"]
        self.policies[policy_id].status = "RESOLVED" if decision != -1 else "ACTIVE"
        self.policies[policy_id].decision = decision
        self.policies[policy_id].summary = result["summary"]
        self.policies[policy_id].evidence = result["evidence"]
        return {"policy_id": policy_id, "decision": decision, "status": "QUALIFIED" if decision == 1 else "NOT_QUALIFIED" if decision == 0 else "UNDETERMINED", "summary": result["summary"], "evidence": result["evidence"]}

    @gl.public.view
    def get_policy(self, policy_id: str) -> dict[str, typing.Any]:
        if policy_id not in self.policies: raise gl.vm.UserError("Policy does not exist.")
        p = self.policies[policy_id]
        return {"policy_id": p.policy_id, "owner": str(p.owner), "flight_number": p.flight_number, "departure_date": p.departure_date, "source_url": p.source_url, "payout_amount": p.payout_amount, "status": p.status, "decision": p.decision, "summary": p.summary, "evidence": p.evidence}

    @gl.public.view
    def get_policies_for_user(self, user_address: str) -> list[dict[str, typing.Any]]:
        user = Address(user_address)
        result = []
        for _, p in self.policies.items():
            if p.owner == user:
                result.append({"policy_id": p.policy_id, "owner": str(p.owner), "flight_number": p.flight_number, "departure_date": p.departure_date, "source_url": p.source_url, "payout_amount": p.payout_amount, "status": p.status, "decision": p.decision, "summary": p.summary, "evidence": p.evidence})
        return result
