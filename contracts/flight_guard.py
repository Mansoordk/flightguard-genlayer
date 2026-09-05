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
    def create_policy(
        self,
        flight_number: str,
        departure_date: str,
        source_url: str,
        payout_amount: str,
    ) -> str:

        flight_number = flight_number.strip().upper()
        departure_date = departure_date.strip()
        source_url = source_url.strip()
        payout_amount = payout_amount.strip()

        if not flight_number:
            raise gl.vm.UserError("Flight number is required.")

        if not departure_date:
            raise gl.vm.UserError("Departure date is required.")

        if not source_url.startswith("https://"):
            raise gl.vm.UserError(
                "Source URL must start with https://"
            )

        if not payout_amount:
            raise gl.vm.UserError(
                "Protection amount is required."
            )

        policy_id = str(self.next_policy_id)

        self.policies[policy_id] = FlightPolicy(
            policy_id,
            gl.message.sender_address,
            flight_number,
            departure_date,
            source_url,
            payout_amount,
            "ACTIVE",
            -1,
            "Waiting for flight evaluation.",
            "",
        )

        self.next_policy_id += 1

        return policy_id

    @gl.public.write
    def evaluate_policy(
        self,
        policy_id: str,
    ) -> typing.Any:

        if policy_id not in self.policies:
            raise gl.vm.UserError(
                "Policy does not exist."
            )

        policy = gl.storage.copy_to_memory(
            self.policies[policy_id]
        )

        if policy.status == "RESOLVED":
            raise gl.vm.UserError(
                "This policy has already been resolved."
            )

        flight_number = policy.flight_number
        departure_date = policy.departure_date
        source_url = policy.source_url

        # ---------------------------------------------------------
        # Consensus-critical flight evaluation
        # ---------------------------------------------------------
        def evaluate_source():

            web_data = gl.nondet.web.render(
                source_url,
                mode="text",
                wait_after_loaded="3s",
            )

            prompt = f"""
You are a strict flight-disruption evidence evaluator.

TARGET FLIGHT:
{flight_number}

TARGET DEPARTURE DATE:
{departure_date}

SOURCE URL:
{source_url}

SOURCE CONTENT:
{web_data}

IMPORTANT:
Use ONLY the supplied source content.

The source must clearly identify BOTH:

1. The exact flight number: {flight_number}
2. The exact departure date: {departure_date}

Never use information from another date.

Never guess missing information.

DECISION RULES:

decision = 1
ONLY when:
- the exact flight is clearly cancelled, OR
- the exact flight has a delay of 120 minutes or more.

decision = 0
when:
- the exact flight is confirmed to have operated normally,
- the exact flight is on time, OR
- the exact flight has a delay of less than 120 minutes.

decision = -1
when:
- the exact flight/date cannot be verified,
- the source contains insufficient evidence,
- the source contains contradictory information,
- the source refers to another date,
- the source is stale or does not provide enough information.

For delay calculations:

If scheduled and actual times are available, calculate the delay.

Examples:

23 minutes late -> decision 0
60 minutes late -> decision 0
119 minutes late -> decision 0
120 minutes late -> decision 1
180 minutes late -> decision 1

A cancellation -> decision 1

If the source explicitly says "cancelled", that is sufficient
evidence for decision 1 when it clearly refers to the exact
flight and target date.

If the source says "on time", that supports decision 0.

If the source shows a small delay but less than 120 minutes,
decision must remain 0.

Do NOT confuse:
- scheduled departure time
- actual departure time
- scheduled arrival time
- actual arrival time

Return ONLY valid JSON.

The JSON MUST have exactly these fields:

{{
    "decision": 0,
    "status": "ON_TIME",
    "delay_minutes": 0
}}

Allowed decision values:

1 = cancelled OR delayed 120 minutes or more
0 = on time OR delayed less than 120 minutes
-1 = insufficient evidence

Allowed status values:

"CANCELLED"
"DELAYED"
"ON_TIME"
"INSUFFICIENT_EVIDENCE"

delay_minutes rules:

- Use the calculated delay when reliable timing information exists.
- Use 0 for a confirmed cancellation.
- Use 0 when explicitly on time and no meaningful delay is shown.
- Use -1 when there is insufficient evidence.

Do not include explanations outside the JSON object.
"""

            result = gl.nondet.exec_prompt(
                prompt,
                response_format="json",
            )

            if not isinstance(result, dict):
                raise gl.vm.UserError(
                    "LLM did not return an object."
                )

            decision = result.get("decision")
            status = result.get("status")
            delay_minutes = result.get("delay_minutes")

            if decision not in [1, 0, -1]:
                raise gl.vm.UserError(
                    "Invalid decision."
                )

            if status not in [
                "CANCELLED",
                "DELAYED",
                "ON_TIME",
                "INSUFFICIENT_EVIDENCE",
            ]:
                raise gl.vm.UserError(
                    "Invalid status."
                )

            if not isinstance(delay_minutes, int):
                raise gl.vm.UserError(
                    "Invalid delay_minutes."
                )

            if delay_minutes < -1:
                raise gl.vm.UserError(
                    "Invalid delay_minutes value."
                )

            return {
                "decision": decision,
                "status": status,
                "delay_minutes": delay_minutes,
            }

        # ---------------------------------------------------------
        # Validator
        #
        # Validators independently perform the same evaluation.
        # Consensus only depends on the stable "decision" field.
        # ---------------------------------------------------------
        def validator_fn(leader_result) -> bool:

            if not isinstance(
                leader_result,
                gl.vm.Return,
            ):
                return False

            leader = leader_result.calldata

            if not isinstance(
                leader,
                dict,
            ):
                return False

            leader_decision = leader.get(
                "decision"
            )

            if leader_decision not in [1, 0, -1]:
                return False

            try:
                validator_result = evaluate_source()
            except Exception:
                return False

            if not isinstance(
                validator_result,
                dict,
            ):
                return False

            validator_decision = validator_result.get(
                "decision"
            )

            if validator_decision not in [1, 0, -1]:
                return False

            # Consensus-critical comparison:
            # only the actual decision must match.
            return (
                validator_decision
                == leader_decision
            )

        # ---------------------------------------------------------
        # Run GenLayer non-deterministic consensus
        # ---------------------------------------------------------
        result = gl.vm.run_nondet_unsafe(
            evaluate_source,
            validator_fn,
        )

        decision = result["decision"]
        status = result["status"]
        delay_minutes = result["delay_minutes"]

        # ---------------------------------------------------------
        # Store final policy state
        # ---------------------------------------------------------

        if decision == -1:
            policy_status = "ACTIVE"
        else:
            policy_status = "RESOLVED"

        self.policies[policy_id].status = policy_status
        self.policies[policy_id].decision = decision

        # ---------------------------------------------------------
        # Human-readable summary
        # ---------------------------------------------------------

        if decision == 1:

            if status == "CANCELLED":
                summary = (
                    "The flight was cancelled according to "
                    "the supplied flight-status evidence."
                )

            elif delay_minutes >= 120:
                summary = (
                    f"The flight experienced a delay of "
                    f"{delay_minutes} minutes, meeting the "
                    f"120-minute protection threshold."
                )

            else:
                summary = (
                    "The flight qualified for protection "
                    "based on the supplied evidence."
                )

        elif decision == 0:

            if status == "DELAYED":
                summary = (
                    f"The flight delay was "
                    f"{delay_minutes} minutes, which is below "
                    f"the 120-minute protection threshold."
                )

            else:
                summary = (
                    "The flight did not meet the "
                    "120-minute disruption threshold."
                )

        else:

            summary = (
                "There was insufficient reliable evidence "
                "to determine whether the flight qualifies."
            )

        # ---------------------------------------------------------
        # Evidence stored on-chain
        # ---------------------------------------------------------

        if status == "CANCELLED":

            evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: cancellation confirmed "
                f"by the supplied source."
            )

        elif status == "DELAYED":

            evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: reported delay "
                f"of {delay_minutes} minutes."
            )

        elif status == "ON_TIME":

            evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: source indicates "
                f"the flight operated on time."
            )

        else:

            evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: the supplied source "
                f"did not provide sufficient evidence."
            )

        self.policies[policy_id].summary = summary
        self.policies[policy_id].evidence = evidence

        # ---------------------------------------------------------
        # Return evaluation result
        # ---------------------------------------------------------

        return {
            "policy_id": policy_id,
            "decision": decision,
            "status": (
                "QUALIFIED"
                if decision == 1
                else "NOT_QUALIFIED"
                if decision == 0
                else "UNDETERMINED"
            ),
            "summary": summary,
            "evidence": evidence,
        }

    @gl.public.view
    def get_policy(
        self,
        policy_id: str,
    ) -> dict[str, typing.Any]:

        if policy_id not in self.policies:
            raise gl.vm.UserError(
                "Policy does not exist."
            )

        p = self.policies[policy_id]

        return {
            "policy_id": p.policy_id,
            "owner": str(p.owner),
            "flight_number": p.flight_number,
            "departure_date": p.departure_date,
            "source_url": p.source_url,
            "payout_amount": p.payout_amount,
            "status": p.status,
            "decision": p.decision,
            "summary": p.summary,
            "evidence": p.evidence,
        }

    @gl.public.view
    def get_policies_for_user(
        self,
        user_address: str,
    ) -> list[dict[str, typing.Any]]:

        user = Address(user_address)

        result = []

        for _, p in self.policies.items():

            if p.owner == user:

                result.append(
                    {
                        "policy_id": p.policy_id,
                        "owner": str(p.owner),
                        "flight_number": p.flight_number,
                        "departure_date": p.departure_date,
                        "source_url": p.source_url,
                        "payout_amount": p.payout_amount,
                        "status": p.status,
                        "decision": p.decision,
                        "summary": p.summary,
                        "evidence": p.evidence,
                    }
                )

        return result