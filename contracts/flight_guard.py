# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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

    # ---------------------------------------------------------
    # TRUST MODEL
    #
    # Only established flight-status sources are accepted.
    # This prevents users from supplying arbitrary websites.
    # ---------------------------------------------------------
    TRUSTED_SOURCE_PREFIXES = (
        "https://flightaware.com/",
        "https://www.flightaware.com/",
        "https://flightradar24.com/",
        "https://www.flightradar24.com/",
    )

    # ---------------------------------------------------------
    # EVALUATION WINDOW
    #
    # The policy may be evaluated from:
    #
    #   1 day before departure
    #   through
    #   2 days after departure
    #
    # This is intentionally based on the departure DATE because
    # the existing policy only stores a date, not an exact
    # departure timestamp.
    # ---------------------------------------------------------
    WINDOW_START_OFFSET = timedelta(days=-1)
    WINDOW_END_OFFSET = timedelta(days=2)

    def __init__(self):
        self.next_policy_id = 1

    # ---------------------------------------------------------
    # TRUSTED SOURCE VALIDATION
    # ---------------------------------------------------------

    def _is_trusted_source(
        self,
        source_url: str,
    ) -> bool:

        normalized = source_url.strip().lower()

        for prefix in self.TRUSTED_SOURCE_PREFIXES:

            if normalized.startswith(prefix):
                return True

        return False

    # ---------------------------------------------------------
    # DEPARTURE DATE VALIDATION
    # ---------------------------------------------------------

    def _parse_departure_date(
        self,
        departure_date: str,
    ) -> datetime:

        try:

            return datetime.strptime(
                departure_date,
                "%Y-%m-%d",
            ).replace(
                tzinfo=timezone.utc
            )

        except Exception:

            raise gl.vm.UserError(
                "Departure date must use YYYY-MM-DD format."
            )

    # ---------------------------------------------------------
    # EVALUATION WINDOW
    # ---------------------------------------------------------

    def _evaluation_window(
        self,
        departure_date: str,
    ) -> typing.Tuple[datetime, datetime]:

        departure = self._parse_departure_date(
            departure_date
        )

        window_start = (
            departure
            + self.WINDOW_START_OFFSET
        )

        window_end = (
            departure
            + self.WINDOW_END_OFFSET
        )

        return (
            window_start,
            window_end,
        )

    # ---------------------------------------------------------
    # WINDOW STATE
    # ---------------------------------------------------------

    def _window_state(
        self,
        departure_date: str,
    ) -> str:

        now = datetime.now(
            timezone.utc
        )

        window_start, window_end = (
            self._evaluation_window(
                departure_date
            )
        )

        if now < window_start:
            return "NOT_OPEN"

        if now > window_end:
            return "CLOSED"

        return "OPEN"

    @gl.public.write
    def create_policy(
        self,
        flight_number: str,
        departure_date: str,
        source_url: str,
        payout_amount: str,
    ) -> str:

        flight_number = (
            flight_number.strip().upper()
        )

        departure_date = (
            departure_date.strip()
        )

        source_url = (
            source_url.strip()
        )

        payout_amount = (
            payout_amount.strip()
        )

        if not flight_number:

            raise gl.vm.UserError(
                "Flight number is required."
            )

        if not departure_date:

            raise gl.vm.UserError(
                "Departure date is required."
            )

        # Validate date format during creation so that an
        # invalid date can never create a policy.
        self._parse_departure_date(
            departure_date
        )

        if not source_url.startswith(
            "https://"
        ):

            raise gl.vm.UserError(
                "Source URL must start with https://"
            )

        # -----------------------------------------------------
        # TRUST MODEL
        #
        # Reject arbitrary websites.
        # Only FlightAware and Flightradar24 are accepted.
        # -----------------------------------------------------

        if not self._is_trusted_source(
            source_url
        ):

            raise gl.vm.UserError(
                "Source must be FlightAware or Flightradar24."
            )

        if not payout_amount:

            raise gl.vm.UserError(
                "Protection amount is required."
            )

        policy_id = str(
            self.next_policy_id
        )

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

        flight_number = (
            policy.flight_number
        )

        departure_date = (
            policy.departure_date
        )

        source_url = (
            policy.source_url
        )

        # ---------------------------------------------------------
        # TRUST MODEL CHECK
        #
        # This protects policies even if an old/incompatible
        # policy somehow exists in storage.
        # ---------------------------------------------------------

        if not self._is_trusted_source(
            source_url
        ):

            raise gl.vm.UserError(
                "Policy source is not a trusted flight-status source."
            )

        # ---------------------------------------------------------
        # EVALUATION WINDOW
        #
        # A policy cannot be resolved before its window opens.
        # A policy cannot be resolved after its window closes.
        # ---------------------------------------------------------

        window_state = self._window_state(
            departure_date
        )

        if window_state == "NOT_OPEN":

            raise gl.vm.UserError(
                "The flight evaluation window has not opened yet."
            )

        if window_state == "CLOSED":

            # Do NOT raise after changing storage.
            # A raised UserError can revert the state change.
            self.policies[policy_id].status = (
                "EXPIRED"
            )

            self.policies[policy_id].decision = -1

            self.policies[policy_id].summary = (
                "The evaluation window has closed "
                "without a valid policy resolution."
            )

            self.policies[policy_id].evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: evaluation attempted "
                f"outside the valid evaluation window."
            )

            return {
                "policy_id": policy_id,
                "decision": -1,
                "status": "EXPIRED",
                "summary": (
                    "The evaluation window has closed "
                    "without a valid policy resolution."
                ),
                "evidence": (
                    f"Flight {flight_number} on "
                    f"{departure_date}: evaluation attempted "
                    f"outside the valid evaluation window."
                ),
            }

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

            if not isinstance(
                result,
                dict,
            ):

                raise gl.vm.UserError(
                    "LLM did not return an object."
                )

            decision = result.get(
                "decision"
            )

            status = result.get(
                "status"
            )

            delay_minutes = result.get(
                "delay_minutes"
            )

            if decision not in [
                1,
                0,
                -1,
            ]:

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

            if not isinstance(
                delay_minutes,
                int,
            ):

                raise gl.vm.UserError(
                    "Invalid delay_minutes."
                )

            if delay_minutes < -1:

                raise gl.vm.UserError(
                    "Invalid delay_minutes value."
                )

            # -----------------------------------------------------
            # Additional consistency checks.
            #
            # Prevent a result such as:
            # decision=1 + ON_TIME
            # decision=0 + CANCELLED
            # -----------------------------------------------------

            if decision == 1:

                if status == "ON_TIME":

                    raise gl.vm.UserError(
                        "Inconsistent flight evaluation."
                    )

                if (
                    status == "DELAYED"
                    and delay_minutes < 120
                ):

                    raise gl.vm.UserError(
                        "Delay does not meet protection threshold."
                    )

            if decision == 0:

                if status == "CANCELLED":

                    raise gl.vm.UserError(
                        "Inconsistent flight evaluation."
                    )

                if (
                    status == "DELAYED"
                    and delay_minutes >= 120
                ):

                    raise gl.vm.UserError(
                        "Delay meets protection threshold."
                    )

            if decision == -1:

                if status != "INSUFFICIENT_EVIDENCE":

                    raise gl.vm.UserError(
                        "Insufficient evidence must use the correct status."
                    )

                if delay_minutes != -1:

                    raise gl.vm.UserError(
                        "Insufficient evidence must use delay_minutes -1."
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

        def validator_fn(
            leader_result
        ) -> bool:

            if not isinstance(
                leader_result,
                gl.vm.Return,
            ):

                return False

            leader = (
                leader_result.calldata
            )

            if not isinstance(
                leader,
                dict,
            ):

                return False

            leader_decision = (
                leader.get("decision")
            )

            if leader_decision not in [
                1,
                0,
                -1,
            ]:

                return False

            try:

                validator_result = (
                    evaluate_source()
                )

            except Exception:

                return False

            if not isinstance(
                validator_result,
                dict,
            ):

                return False

            validator_decision = (
                validator_result.get(
                    "decision"
                )
            )

            if validator_decision not in [
                1,
                0,
                -1,
            ]:

                return False

            # Consensus-critical comparison:
            # only the actual policy decision must match.
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

        decision = result[
            "decision"
        ]

        status = result[
            "status"
        ]

        delay_minutes = result[
            "delay_minutes"
        ]

        # ---------------------------------------------------------
        # Store final policy state
        # ---------------------------------------------------------

        if decision == -1:

            policy_status = "ACTIVE"

        else:

            policy_status = "RESOLVED"

        self.policies[
            policy_id
        ].status = policy_status

        self.policies[
            policy_id
        ].decision = decision

        # ---------------------------------------------------------
        # Human-readable summary
        # ---------------------------------------------------------

        if decision == 1:

            if status == "CANCELLED":

                summary = (
                    "The flight was cancelled according to "
                    "the trusted flight-status source."
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
                    "based on the supplied flight-status evidence."
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
                f"by the trusted flight-status source."
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
                f"{departure_date}: trusted source indicates "
                f"the flight operated on time."
            )

        else:

            evidence = (
                f"Flight {flight_number} on "
                f"{departure_date}: the trusted source "
                f"did not provide sufficient evidence."
            )

        self.policies[
            policy_id
        ].summary = summary

        self.policies[
            policy_id
        ].evidence = evidence

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

        p = self.policies[
            policy_id
        ]

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

        user = Address(
            user_address
        )

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