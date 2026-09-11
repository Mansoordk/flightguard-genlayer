# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import typing


@allow_storage
@dataclass
class FlightPolicy:
    policy_id: str
    owner: Address

    flight_number: str
    departure_date: str

    source_url: str
    corroborating_source_url: str

    payout_amount: str

    status: str
    # ACTIVE = waiting for valid evaluation / insufficient evidence
    # RESOLVED = final qualifying or non-qualifying decision
    # EXPIRED = evaluation window has closed

    decision: i8
    # 1  = qualified
    # 0  = not qualified
    # -1 = undetermined

    summary: str
    evidence: str

    evaluation_start: str
    evaluation_end: str


class FlightGuard(gl.Contract):

    policies: TreeMap[str, FlightPolicy]
    next_policy_id: u256

    # ============================================================
    # TRUSTED SOURCE CONFIGURATION
    # ============================================================

    TRUSTED_SOURCE_DOMAINS = (
        "flightaware.com",
        "flightradar24.com",
    )

    # ============================================================
    # EVALUATION WINDOW
    #
    # Because the application stores only YYYY-MM-DD and not the
    # exact scheduled departure timestamp:
    #
    # Opens: 24 hours before departure date at 00:00 UTC
    # Closes: 48 hours after departure date at 00:00 UTC
    #
    # Example:
    #
    # departure_date = 2026-09-10
    #
    # evaluation_start = 2026-09-09T00:00:00+00:00
    # evaluation_end   = 2026-09-12T00:00:00+00:00
    # ============================================================

    WINDOW_START_OFFSET = timedelta(days=-1)
    WINDOW_END_OFFSET = timedelta(days=2)

    def __init__(self):
        self.next_policy_id = 1

    # ============================================================
    # URL / SOURCE HELPERS
    # ============================================================

    def _extract_host(self, url: str) -> str:

        if not url.startswith("https://"):
            return ""

        remainder = url[len("https://"):]

        # Remove path
        remainder = remainder.split("/", 1)[0]

        # Remove query
        remainder = remainder.split("?", 1)[0]

        # Remove fragment
        remainder = remainder.split("#", 1)[0]

        # Remove port
        remainder = remainder.split(":", 1)[0]

        host = remainder.strip().lower()

        if host.startswith("www."):
            host = host[4:]

        return host

    def _is_trusted_source(self, url: str) -> bool:

        host = self._extract_host(url)

        if not host:
            return False

        # Exact host matching.
        #
        # We deliberately do NOT accept arbitrary subdomains.
        # This prevents something like:
        #
        # evil.flightaware.com
        #
        # from being treated as an official source.
        for domain in self.TRUSTED_SOURCE_DOMAINS:
            if host == domain:
                return True

        return False

    def _source_domain(self, url: str) -> str:
        return self._extract_host(url)

    # ============================================================
    # DATE / EVALUATION WINDOW HELPERS
    # ============================================================

    def _parse_departure_date(self, departure_date: str) -> datetime:

        try:
            return datetime.strptime(
                departure_date,
                "%Y-%m-%d",
            ).replace(tzinfo=timezone.utc)

        except Exception:
            raise gl.vm.UserError(
                "Departure date must use YYYY-MM-DD format."
            )

    def _evaluation_window(
        self,
        departure_date: str,
    ) -> tuple[str, str]:

        departure_day = self._parse_departure_date(
            departure_date
        )

        start = (
            departure_day
            + self.WINDOW_START_OFFSET
        )

        end = (
            departure_day
            + self.WINDOW_END_OFFSET
        )

        return (
            start.isoformat(),
            end.isoformat(),
        )

    def _window_state(
        self,
        departure_date: str,
    ) -> str:

        departure_day = self._parse_departure_date(
            departure_date
        )

        now = datetime.now(timezone.utc)

        window_start = (
            departure_day
            + self.WINDOW_START_OFFSET
        )

        window_end = (
            departure_day
            + self.WINDOW_END_OFFSET
        )

        if now < window_start:
            return "NOT_OPEN"

        if now >= window_end:
            return "CLOSED"

        return "OPEN"

    # ============================================================
    # SINGLE SOURCE EVALUATION
    # ============================================================

    def _evaluate_single_source(
        self,
        source_url: str,
        flight_number: str,
        departure_date: str,
    ) -> dict[str, typing.Any]:

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

============================================================
IDENTITY REQUIREMENTS
============================================================

Use ONLY the supplied source content.

The source must clearly identify BOTH:

1. The exact flight number:
   {flight_number}

2. The exact departure date:
   {departure_date}

Do NOT use information from another date.

Do NOT infer the target flight's status from another flight.

Do NOT guess missing information.

If the source cannot clearly connect the evidence to BOTH
the target flight number and target departure date,
return decision = -1.

============================================================
DECISION RULES
============================================================

decision = 1 ONLY when:

- the exact flight is clearly cancelled, OR
- the exact flight has a delay of 120 minutes or more.

decision = 0 when:

- the exact flight is confirmed on time, OR
- the exact flight operated normally, OR
- the exact flight has a delay below 120 minutes.

decision = -1 when:

- the exact flight cannot be verified,
- the exact departure date cannot be verified,
- evidence is insufficient,
- evidence is contradictory,
- the source is stale,
- the source refers to another date,
- or the source does not contain enough information.

============================================================
DELAY RULES
============================================================

120 minutes = QUALIFYING

119 minutes = NOT QUALIFYING

180 minutes = QUALIFYING

23 minutes = NOT QUALIFYING

If the source explicitly says the flight was cancelled,
that qualifies as decision = 1 when the exact flight/date
are verified.

If scheduled and actual times are available, calculate the
delay from those times.

Do not confuse:

- scheduled departure
- actual departure
- scheduled arrival
- actual arrival

============================================================
STATUS VALUES
============================================================

Allowed status values:

"CANCELLED"
"DELAYED"
"ON_TIME"
"INSUFFICIENT_EVIDENCE"

If decision = -1:

status MUST be "INSUFFICIENT_EVIDENCE".

If status = "CANCELLED":

decision MUST be 1.

If status = "DELAYED":

decision is:

1 if delay >= 120
0 if delay < 120

If status = "ON_TIME":

decision MUST be 0.

============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

The JSON MUST contain exactly:

{{
    "decision": 0,
    "status": "ON_TIME",
    "delay_minutes": 0
}}

Rules for delay_minutes:

- Reliable calculated delay -> use the calculated value.
- Confirmed cancellation -> use 0.
- Explicitly on time -> use 0.
- Insufficient evidence -> use -1.

No explanation outside the JSON object.
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

        # --------------------------------------------------------
        # Validate decision
        # --------------------------------------------------------

        if decision not in [1, 0, -1]:
            raise gl.vm.UserError(
                "Invalid decision returned by evaluator."
            )

        # --------------------------------------------------------
        # Validate status
        # --------------------------------------------------------

        if status not in [
            "CANCELLED",
            "DELAYED",
            "ON_TIME",
            "INSUFFICIENT_EVIDENCE",
        ]:
            raise gl.vm.UserError(
                "Invalid flight status returned by evaluator."
            )

        # --------------------------------------------------------
        # Validate delay
        # --------------------------------------------------------

        if not isinstance(delay_minutes, int):
            raise gl.vm.UserError(
                "Invalid delay_minutes returned by evaluator."
            )

        if delay_minutes < -1:
            raise gl.vm.UserError(
                "Invalid delay_minutes value."
            )

        # --------------------------------------------------------
        # Enforce internal consistency
        # --------------------------------------------------------

        if decision == -1:

            if status != "INSUFFICIENT_EVIDENCE":
                raise gl.vm.UserError(
                    "Undetermined decision must use "
                    "INSUFFICIENT_EVIDENCE status."
                )

            delay_minutes = -1

        elif status == "CANCELLED":

            if decision != 1:
                raise gl.vm.UserError(
                    "Cancelled flight must qualify."
                )

            delay_minutes = 0

        elif status == "DELAYED":

            if delay_minutes < 0:
                raise gl.vm.UserError(
                    "Delayed flight must have a valid delay."
                )

            expected_decision = (
                1 if delay_minutes >= 120 else 0
            )

            if decision != expected_decision:
                raise gl.vm.UserError(
                    "Delay and decision are inconsistent."
                )

        elif status == "ON_TIME":

            if decision != 0:
                raise gl.vm.UserError(
                    "On-time flight cannot qualify."
                )

            delay_minutes = 0

        return {
            "decision": decision,
            "status": status,
            "delay_minutes": delay_minutes,
        }

    # ============================================================
    # CORROBORATED EVALUATION
    # ============================================================

    def _evaluate_sources(
        self,
        source_url: str,
        corroborating_source_url: str,
        flight_number: str,
        departure_date: str,
    ) -> dict[str, typing.Any]:

        primary = self._evaluate_single_source(
            source_url,
            flight_number,
            departure_date,
        )

        corroborating = self._evaluate_single_source(
            corroborating_source_url,
            flight_number,
            departure_date,
        )

        primary_decision = primary["decision"]
        corroborating_decision = corroborating["decision"]

        # --------------------------------------------------------
        # BOTH SOURCES QUALIFY
        # --------------------------------------------------------

        if (
            primary_decision == 1
            and corroborating_decision == 1
        ):

            # If either source explicitly says cancelled,
            # preserve cancellation as the final status.
            if (
                primary["status"] == "CANCELLED"
                or corroborating["status"] == "CANCELLED"
            ):
                final_status = "CANCELLED"
                final_delay = 0

            else:
                final_status = "DELAYED"

                final_delay = max(
                    primary["delay_minutes"],
                    corroborating["delay_minutes"],
                )

            return {
                "decision": 1,
                "status": final_status,
                "delay_minutes": final_delay,
                "primary_decision": primary_decision,
                "corroborating_decision": corroborating_decision,
            }

        # --------------------------------------------------------
        # BOTH SOURCES DO NOT QUALIFY
        # --------------------------------------------------------

        if (
            primary_decision == 0
            and corroborating_decision == 0
        ):

            if (
                primary["status"] == "DELAYED"
                or corroborating["status"] == "DELAYED"
            ):

                final_status = "DELAYED"

                delays = []

                if primary["status"] == "DELAYED":
                    delays.append(
                        primary["delay_minutes"]
                    )

                if corroborating["status"] == "DELAYED":
                    delays.append(
                        corroborating["delay_minutes"]
                    )

                final_delay = max(delays)

            else:

                final_status = "ON_TIME"
                final_delay = 0

            return {
                "decision": 0,
                "status": final_status,
                "delay_minutes": final_delay,
                "primary_decision": primary_decision,
                "corroborating_decision": corroborating_decision,
            }

        # --------------------------------------------------------
        # DISAGREEMENT / INSUFFICIENT EVIDENCE
        # --------------------------------------------------------

        return {
            "decision": -1,
            "status": "INSUFFICIENT_EVIDENCE",
            "delay_minutes": -1,
            "primary_decision": primary_decision,
            "corroborating_decision": corroborating_decision,
        }

    # ============================================================
    # CREATE POLICY
    # ============================================================

    @gl.public.write
    def create_policy(
        self,
        flight_number: str,
        departure_date: str,
        source_url: str,
        payout_amount: str,
        corroborating_source_url: str,
    ) -> str:

        flight_number = flight_number.strip().upper()
        departure_date = departure_date.strip()
        source_url = source_url.strip()
        payout_amount = payout_amount.strip()
        corroborating_source_url = (
            corroborating_source_url.strip()
        )

        # --------------------------------------------------------
        # Basic validation
        # --------------------------------------------------------

        if not flight_number:
            raise gl.vm.UserError(
                "Flight number is required."
            )

        if not departure_date:
            raise gl.vm.UserError(
                "Departure date is required."
            )

        if not source_url.startswith("https://"):
            raise gl.vm.UserError(
                "Primary source URL must start with https://"
            )

        if not corroborating_source_url.startswith("https://"):
            raise gl.vm.UserError(
                "Corroborating source URL must start with https://"
            )

        if not payout_amount:
            raise gl.vm.UserError(
                "Protection amount is required."
            )

        # --------------------------------------------------------
        # Validate date
        # --------------------------------------------------------

        evaluation_start, evaluation_end = (
            self._evaluation_window(
                departure_date
            )
        )

        # --------------------------------------------------------
        # Validate trusted sources
        # --------------------------------------------------------

        if not self._is_trusted_source(source_url):
            raise gl.vm.UserError(
                "Primary source is not approved. "
                "Use FlightAware or Flightradar24."
            )

        if not self._is_trusted_source(
            corroborating_source_url
        ):
            raise gl.vm.UserError(
                "Corroborating source is not approved. "
                "Use FlightAware or Flightradar24."
            )

        primary_domain = self._source_domain(
            source_url
        )

        corroborating_domain = self._source_domain(
            corroborating_source_url
        )

        # --------------------------------------------------------
        # Require independent domains
        # --------------------------------------------------------

        if primary_domain == corroborating_domain:
            raise gl.vm.UserError(
                "The two evidence sources must come "
                "from different domains."
            )

        # --------------------------------------------------------
        # Create policy
        # --------------------------------------------------------

        policy_id = str(self.next_policy_id)

        self.policies[policy_id] = FlightPolicy(
            policy_id,
            gl.message.sender_address,

            flight_number,
            departure_date,

            source_url,
            corroborating_source_url,

            payout_amount,

            "ACTIVE",
            -1,

            "Waiting for the valid evaluation window.",
            "",

            evaluation_start,
            evaluation_end,
        )

        self.next_policy_id += 1

        return policy_id

    # ============================================================
    # EVALUATE POLICY
    # ============================================================

    @gl.public.write
    def evaluate_policy(
        self,
        policy_id: str,
    ) -> typing.Any:

        # --------------------------------------------------------
        # Policy existence
        # --------------------------------------------------------

        if policy_id not in self.policies:
            raise gl.vm.UserError(
                "Policy does not exist."
            )

        policy = gl.storage.copy_to_memory(
            self.policies[policy_id]
        )

        # --------------------------------------------------------
        # Existing resolution state
        # --------------------------------------------------------

        if policy.status == "RESOLVED":
            raise gl.vm.UserError(
                "This policy has already been resolved."
            )

        if policy.status == "EXPIRED":
            raise gl.vm.UserError(
                "This policy has expired."
            )

        # --------------------------------------------------------
        # Evaluation window
        # --------------------------------------------------------

        window_state = self._window_state(
            policy.departure_date
        )

        # --------------------------------------------------------
        # Too early
        # --------------------------------------------------------

        if window_state == "NOT_OPEN":

            raise gl.vm.UserError(
                "The evaluation window has not opened yet. "
                "The policy cannot be resolved before "
                "the valid evaluation window."
            )

        # --------------------------------------------------------
        # Too late
        #
        # IMPORTANT:
        #
        # We persist EXPIRED and return normally.
        # We do NOT write state and then raise an error.
        # --------------------------------------------------------

        if window_state == "CLOSED":

            self.policies[policy_id].status = "EXPIRED"

            self.policies[policy_id].decision = -1

            self.policies[policy_id].summary = (
                "The evaluation window closed before "
                "a valid policy resolution was completed."
            )

            self.policies[policy_id].evidence = (
                "No policy resolution is permitted "
                "after the configured evaluation window."
            )

            return {
                "policy_id": policy_id,
                "decision": -1,
                "status": "EXPIRED",
                "contract_state": "EXPIRED",
                "summary": (
                    "The evaluation window closed before "
                    "a valid policy resolution was completed."
                ),
                "evidence": (
                    "No policy resolution is permitted "
                    "after the configured evaluation window."
                ),
                "evaluation_start": (
                    policy.evaluation_start
                ),
                "evaluation_end": (
                    policy.evaluation_end
                ),
            }

        # --------------------------------------------------------
        # Copy deterministic policy data to local variables.
        #
        # Nondeterministic functions must not access storage.
        # --------------------------------------------------------

        flight_number = policy.flight_number
        departure_date = policy.departure_date

        source_url = policy.source_url
        corroborating_source_url = (
            policy.corroborating_source_url
        )

        # ========================================================
        # NONDETERMINISTIC LEADER EVALUATION
        # ========================================================

        def leader_fn():

            return self._evaluate_sources(
                source_url,
                corroborating_source_url,
                flight_number,
                departure_date,
            )

        # ========================================================
        # VALIDATOR
        #
        # Validator independently retrieves and evaluates both
        # sources.
        #
        # We validate the structure and consensus-critical
        # decision rather than requiring identical LLM wording
        # or identical delay numbers.
        # ========================================================

        def validator_fn(
            leader_result,
        ) -> bool:

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

            # ----------------------------------------------------
            # Validate leader decision
            # ----------------------------------------------------

            leader_decision = leader.get(
                "decision"
            )

            leader_status = leader.get(
                "status"
            )

            leader_delay = leader.get(
                "delay_minutes"
            )

            leader_primary = leader.get(
                "primary_decision"
            )

            leader_corroborating = leader.get(
                "corroborating_decision"
            )

            if leader_decision not in [
                1,
                0,
                -1,
            ]:
                return False

            if leader_status not in [
                "CANCELLED",
                "DELAYED",
                "ON_TIME",
                "INSUFFICIENT_EVIDENCE",
            ]:
                return False

            if not isinstance(
                leader_delay,
                int,
            ):
                return False

            if leader_primary not in [
                1,
                0,
                -1,
            ]:
                return False

            if leader_corroborating not in [
                1,
                0,
                -1,
            ]:
                return False

            # ----------------------------------------------------
            # Validate leader's corroboration logic
            # ----------------------------------------------------

            if (
                leader_primary == 1
                and leader_corroborating == 1
            ):

                if leader_decision != 1:
                    return False

            elif (
                leader_primary == 0
                and leader_corroborating == 0
            ):

                if leader_decision != 0:
                    return False

            else:

                if leader_decision != -1:
                    return False

            # ----------------------------------------------------
            # Independently evaluate both sources
            # ----------------------------------------------------

            try:

                validator_result = self._evaluate_sources(
                    source_url,
                    corroborating_source_url,
                    flight_number,
                    departure_date,
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

            validator_status = (
                validator_result.get(
                    "status"
                )
            )

            validator_delay = (
                validator_result.get(
                    "delay_minutes"
                )
            )

            validator_primary = (
                validator_result.get(
                    "primary_decision"
                )
            )

            validator_corroborating = (
                validator_result.get(
                    "corroborating_decision"
                )
            )

            # ----------------------------------------------------
            # Validate validator result
            # ----------------------------------------------------

            if validator_decision not in [
                1,
                0,
                -1,
            ]:
                return False

            if validator_status not in [
                "CANCELLED",
                "DELAYED",
                "ON_TIME",
                "INSUFFICIENT_EVIDENCE",
            ]:
                return False

            if not isinstance(
                validator_delay,
                int,
            ):
                return False

            if validator_primary not in [
                1,
                0,
                -1,
            ]:
                return False

            if validator_corroborating not in [
                1,
                0,
                -1,
            ]:
                return False

            # ----------------------------------------------------
            # Validate validator's corroboration logic
            # ----------------------------------------------------

            if (
                validator_primary == 1
                and validator_corroborating == 1
            ):

                if validator_decision != 1:
                    return False

            elif (
                validator_primary == 0
                and validator_corroborating == 0
            ):

                if validator_decision != 0:
                    return False

            else:

                if validator_decision != -1:
                    return False

            # ----------------------------------------------------
            # Consensus-critical comparison
            #
            # The final policy decision must agree.
            # ----------------------------------------------------

            if validator_decision != leader_decision:
                return False

            return True

        # ========================================================
        # RUN GENLAYER CONSENSUS
        # ========================================================

        result = gl.vm.run_nondet_unsafe(
            leader_fn,
            validator_fn,
        )

        # ========================================================
        # CONSENSUS RESULT
        # ========================================================

        decision = result["decision"]

        status = result["status"]

        delay_minutes = result[
            "delay_minutes"
        ]

        primary_decision = result[
            "primary_decision"
        ]

        corroborating_decision = result[
            "corroborating_decision"
        ]

        primary_domain = self._source_domain(
            source_url
        )

        corroborating_domain = (
            self._source_domain(
                corroborating_source_url
            )
        )

        # ========================================================
        # DETERMINE CONTRACT STATE
        # ========================================================

        if decision == -1:

            # Important:
            #
            # Insufficient or conflicting evidence does NOT
            # permanently resolve the policy.
            #
            # The policy remains ACTIVE and can be evaluated
            # again while the evaluation window remains open.

            policy_status = "ACTIVE"

        else:

            # Only a corroborated consensus-backed decision
            # inside the valid evaluation window resolves the
            # policy.

            policy_status = "RESOLVED"

        # ========================================================
        # HUMAN-READABLE SUMMARY
        # ========================================================

        if decision == 1:

            if status == "CANCELLED":

                summary = (
                    "Both trusted flight-status sources "
                    "indicated that the flight was cancelled."
                )

            else:

                summary = (
                    "Both trusted flight-status sources "
                    "supported a qualifying delay of at least "
                    "120 minutes. "
                    f"Reported delay: {delay_minutes} minutes."
                )

        elif decision == 0:

            if status == "DELAYED":

                summary = (
                    "Both trusted flight-status sources "
                    "supported a delay below the 120-minute "
                    f"protection threshold. "
                    f"Reported delay: {delay_minutes} minutes."
                )

            else:

                summary = (
                    "Both trusted flight-status sources "
                    "supported a non-qualifying flight outcome."
                )

        else:

            if (
                primary_decision
                != corroborating_decision
            ):

                summary = (
                    "The trusted sources disagreed on the "
                    "flight outcome. "
                    f"Source 1 decision: {primary_decision}. "
                    f"Source 2 decision: "
                    f"{corroborating_decision}. "
                    "No reliable decision could be reached."
                )

            else:

                summary = (
                    "The trusted sources did not provide "
                    "sufficient corroborating evidence for "
                    "a reliable decision."
                )

        # ========================================================
        # EVIDENCE
        # ========================================================

        if decision == 1:

            if status == "CANCELLED":

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: both trusted sources "
                    f"supported cancellation "
                    f"({primary_domain} + "
                    f"{corroborating_domain})."
                )

            else:

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: both trusted sources "
                    f"supported a qualifying delay of "
                    f"{delay_minutes} minutes "
                    f"({primary_domain} + "
                    f"{corroborating_domain})."
                )

        elif decision == 0:

            if status == "DELAYED":

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: both trusted sources "
                    f"reported a {delay_minutes}-minute delay, "
                    f"below the 120-minute threshold."
                )

            else:

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: both trusted sources "
                    "supported an on-time/non-qualifying "
                    "outcome."
                )

        else:

            if (
                primary_decision
                != corroborating_decision
            ):

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: trusted sources "
                    f"disagreed "
                    f"({primary_domain}: "
                    f"{primary_decision}, "
                    f"{corroborating_domain}: "
                    f"{corroborating_decision})."
                )

            else:

                evidence = (
                    f"Flight {flight_number} on "
                    f"{departure_date}: trusted sources "
                    "could not provide sufficient "
                    "corroborating evidence."
                )

        # ========================================================
        # STORE FINAL STATE
        # ========================================================

        self.policies[policy_id].status = (
            policy_status
        )

        self.policies[policy_id].decision = (
            decision
        )

        self.policies[policy_id].summary = (
            summary
        )

        self.policies[policy_id].evidence = (
            evidence
        )

        # ========================================================
        # RETURN RESULT
        # ========================================================

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

            "contract_state": policy_status,

            "summary": summary,

            "evidence": evidence,

            "evaluation_start": (
                policy.evaluation_start
            ),

            "evaluation_end": (
                policy.evaluation_end
            ),

            "sources": [
                primary_domain,
                corroborating_domain,
            ],

            "primary_decision": (
                primary_decision
            ),

            "corroborating_decision": (
                corroborating_decision
            ),
        }

    # ============================================================
    # GET POLICY
    # ============================================================

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

            "corroborating_source_url": (
                p.corroborating_source_url
            ),

            "payout_amount": p.payout_amount,

            "status": p.status,

            "decision": p.decision,

            "summary": p.summary,

            "evidence": p.evidence,

            "evaluation_start": (
                p.evaluation_start
            ),

            "evaluation_end": (
                p.evaluation_end
            ),
        }

    # ============================================================
    # GET USER POLICIES
    # ============================================================

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

                        "flight_number": (
                            p.flight_number
                        ),

                        "departure_date": (
                            p.departure_date
                        ),

                        "source_url": (
                            p.source_url
                        ),

                        "corroborating_source_url": (
                            p.corroborating_source_url
                        ),

                        "payout_amount": (
                            p.payout_amount
                        ),

                        "status": p.status,

                        "decision": p.decision,

                        "summary": p.summary,

                        "evidence": p.evidence,

                        "evaluation_start": (
                            p.evaluation_start
                        ),

                        "evaluation_end": (
                            p.evaluation_end
                        ),
                    }
                )

        return result

    # ============================================================
    # TRUSTED SOURCES
    # ============================================================

    @gl.public.view
    def get_trusted_sources(
        self,
    ) -> list[str]:

        return [
            "flightaware.com",
            "flightradar24.com",
        ]

    # ============================================================
    # POLICY STATUS
    # ============================================================

    @gl.public.view
    def get_policy_status(
        self,
        policy_id: str,
    ) -> dict[str, typing.Any]:

        if policy_id not in self.policies:
            raise gl.vm.UserError(
                "Policy does not exist."
            )

        p = self.policies[policy_id]

        window_state = self._window_state(
            p.departure_date
        )

        # If the stored policy is already resolved or expired,
        # those states take precedence over the current window.
        if p.status == "RESOLVED":
            can_evaluate = False

        elif p.status == "EXPIRED":
            can_evaluate = False

        else:
            can_evaluate = (
                window_state == "OPEN"
            )

        return {
            "policy_id": p.policy_id,

            "status": p.status,

            "decision": p.decision,

            "window_state": window_state,

            "evaluation_start": (
                p.evaluation_start
            ),

            "evaluation_end": (
                p.evaluation_end
            ),


            "can_evaluate": can_evaluate,
        }