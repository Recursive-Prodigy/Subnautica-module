import random

BOOT = "Alterra telemetry link re-established. Your biological architecture remains surprisingly intact arec."
SHUTDOWN = "Telemetry link severed. PDA entering low-power standby. Do try to survive without corporate supervision."

# --- HYDRATION PROTOCOLS ---
HYDRATION_DUE_LINES = [
    "Fluid intake recommended. Your biological components are drying out.",
    "Reminder: Organic lifeforms require regular water replenishment. Alterra strongly recommends you seek fluid intake.",
    "Hydration levels falling below optimal threshold. Do find something non-toxic to drink.",
    "Hydration interval reached. While dehydration is technically an option, it is not economically viable."
]

HYDRATION_OVERDUE_LINES = [
    "Warning: Severe dehydration threshold approached. Seek fluid intake immediately.",
    "Vital signs suboptimal. Cellular desiccation in progress. I suggest you consume water before cognitive failure ensues.",
    "Emergency: Fluid reserves critical. At your current rate of water consumption, mummification will commence shortly.",
    "Corporate protocol mandates advising you to drink water. Ignoring this alert may void your biological warranty."
]

# --- NUTRITION PROTOCOLS ---
NUTRITION_DUE_LINES = [
    "Calorie intake recommended. Metabolic output is declining.",
    "Sustenance window reached. Alterra suggests seeking nutrient intake at your earliest convenience.",
    "Your cellular engine requires fuel. Please consume a ration before your efficiency degrades further.",
    "Metabolic check: Calorie replenishment suggested. Treat yourself to sustenance."
]

NUTRITION_OVERDUE_LINES = [
    "Emergency: Starvation imminent. Seek calorie intake immediately.",
    "Warning: Metabolic reserves exhausted. I would hate to see this expensive hardware outlive its pilot.",
    "Sustenance overdue. Continued refusal to feed your organic vessel is statistically correlated with termination.",
    "Warning: Organic collapse risk elevated. Consume nutrients now, or prepare for unscheduled system cessation."
]

# --- LOG CONFIRMATION LINES ---
WATER_LOGGED_LINES = [
    "Fluid assimilation confirmed: {amount} milliliters. Your internal ocean expands.",
    "Intake registered: {amount} milliliters. Hydration level now at {pct} percent of daily quota.",
    "Hydration logged. Cellular machinery functioning with marginally improved compliance.",
    "{amount} milliliters assimilated. Alterra commends your commitment to not withering away."
]

WATER_COMPLETED_LINES = [
    "Daily hydration target achieved at {total} milliliters. Further fluid intake may cause buoyancy irregularities.",
    "Target fluid intake complete. Your cellular salinity is officially optimal.",
    "2500 milliliters achieved. Congratulations, you are now composed of the recommended percentage of water."
]

MEAL_LOGGED_LINES = [
    "{tag} confirmed. Sustenance event {count} of {target} logged. Metabolic collapse postponed.",
    "Nutrient intake registered. Biological chassis refueled. Metabolic timer reset.",
    "{tag} logged. Your blood glucose has momentarily ceased its downward trajectory.",
    "Caloric event {count} catalogued. Efficiency rating restored to acceptable Alterra baselines."
]

SNACK_LOGGED_LINES = [
    "{tag} assimilated. Micro-ration catalogued. Caloric integrity marginally prolonged.",
    "Nutrient snack registered. Blood sugar drop temporarily postponed.",
    "Caloric micro-burst consumed. Alterra acknowledges this between-meal indulgence.",
    "{tag} logged. Metabolic baseline refreshed. Back to survival tasks."
]

MEAL_COMPLETED_LINES = [
    "{tag} logged. Daily sustenance target satisfied. Alterra considers your calorie obligations fulfilled.",
    "Target rations consumed for this operational cycle. Further eating is purely recreational."
]

def get_snack_logged_line(tag: str = "Nutrient Snack") -> str:
    return random.choice(SNACK_LOGGED_LINES).format(tag=tag)

# --- EXERTION & RECOVERY PROTOCOLS ---
EXERCISE_LOGGED_LINES = [
    "Physical exertion catalogued. Alterra reminds you that excessive sweat wastes company-rationed electrolytes.",
    "Cardiovascular strain logged. Your meat chassis has survived another round of voluntary physical torment.",
    "Exertion telemetry integrated. Post-workout recovery protocol initiated and hydration interval compressed.",
    "Workout verified. Metabolic throughput increased. Compensatory fluid intake strongly advised."
]

NAP_LOGGED_LINES = [
    "Rest recovery cycle recorded. Homeostatic sleep pressure partially cleared.",
    "Daytime recovery logged. Circadian alertness dip mitigated.",
    "Short-term biological recharging completed. Cognitive capacity restored to nominal parameters.",
    "Power nap registered. Alterra acknowledges this temporary suspension of employee consciousness."
]

# --- SLEEP EVALUATION LINES ---
SLEEP_SHORT_LINES = [
    "Rest cycle concluded: {hours} hours logged with {interruptions} disruptions. A rather reckless allocation of recovery time.",
    "Warning: Sleep cycle critically insufficient at {hours} hours. Cognitive faculties likely operating on pure delusion.",
    "Awakened after {hours} hours. Cellular regeneration was clearly interrupted. I will expect reduced output today."
]

SLEEP_NOMINAL_LINES = [
    "Rest cycle completed: {hours} hours logged. Biological systems stabilized.",
    "Reboot successful: {hours} hours of cellular repair detected. Vital signs within acceptable tolerance.",
    "Sleep telemetry processed: {hours} hours of unconsciousness recorded. Back to work."
]

# --- ROLLBACK & ARCHIVE LINES ---
INTAKE_RETRACTED_LINES = [
    "Telemetry rollback acknowledged. Expelling erroneous intake record from memory banks.",
    "Intake record expunged. Alterra assumes that substance was either imaginary or promptly regurgitated.",
    "Previous entry deleted. Alterra will overlook this temporary loss of fine motor coordination.",
    "Record purged. Vital telemetry adjusted to reflect your actual physiological state."
]

ARCHIVE_VIEWED_LINES = [
    "Accessing Alterra personnel biometric archives. Historical compliance under review.",
    "Archives loaded. Reviewing biological performance telemetry across previous operational cycles."
]

def get_intake_retracted_line() -> str:
    return random.choice(INTAKE_RETRACTED_LINES)

def get_archive_viewed_line() -> str:
    return random.choice(ARCHIVE_VIEWED_LINES)


# --- DIAGNOSTIC ISSUES, ALTERRA ROASTS & TREND COMMENTARY ---
DIAGNOSTIC_ISSUE_ROASTS = {
    # Sector 1: Metabolic Intake
    "hydration_lag": [
        "a fluid deficit of {gap_ml} milliliters, leaving your brain tissue shrinking like a dehydrated sea sponge",
        "a {gap_ml}-milliliter hydration lag that is visibly throttling synaptic speed"
    ],
    "caloric_lag": [
        "delayed caloric intake, expecting high-level cognition on an empty fuel tank",
        "a mid-day ration deficit that is starving your prefrontal cortex of glucose"
    ],
    # Sector 2: Hygiene & Presentability
    "brush_overdue": [
        "unmitigated oral neglect with zero brushing logged today, rendering close-range conversation a biohazard",
        "skipped dental decontamination, allowing planetary plaque colonies to thrive unchecked"
    ],
    "brush_partial": [
        "incomplete oral sanitation with only one brushing cycle logged so far"
    ],
    "shower_overdue": [
        "overdue dermal decontamination after {days_since} days without a shower, making in-person appearance a corporate liability",
        "a critical shower deficit that classifies your exterior bio-film as an environmental hazard"
    ],
    # Sector 3: Exertion, Rest & Circadian
    "no_sleep_data": [
        "missing sleep archive records"
    ],
    "acute_restriction": [
        "acute sleep restriction at {last_h:.1f} hours last night, leaving your focus running on sheer stubbornness",
        "only {last_h:.1f} hours of sleep last night, sabotaging complex problem-solving"
    ],
    "mild_acute_deficit": [
        "a mild sleep deficit of {last_h:.1f} hours last night",
        "slightly truncated rest at {last_h:.1f} hours"
    ],
    "active_sleep_debt": [
        "{debt_h:.1f} hours of active cumulative sleep debt that past weekend naps cannot magically erase",
        "an unrecovered rest deficit of {debt_h:.1f} hours dragging down mental endurance"
    ],
    "fragmented_sleep": [
        "sleep fragmentation from nocturnal disruptions"
    ],
    "wake_phase_shift": [
        "an abrupt {shift_h:.1f}-hour shift in your wake anchor today"
    ],
    "delayed_circadian": [
        "a delayed circadian sleep phase shifted {delay_h:.1f} hours past target bedtime into deep vampire hours",
        "a nocturnal sleep onset drift of {delay_h:.1f} hours disrupting natural melatonin release"
    ],
    "social_jetlag": [
        "wake-time irregularity of {std_h:.1f} hours causing chronic social jetlag"
    ],
    "recovery_lag": [
        "physical workout strain stacked on top of {debt_h:.1f} hours of sleep debt",
        "muscular fatigue compounded by an unrecovered {debt_h:.1f}-hour rest deficit"
    ],
    "metabolic_overreach": [
        "high weekly physical strain without daytime recovery naps"
    ],
    "sedentary_streak": [
        "zero physical exertion logged across the seven-day window, leaving your chassis in purely decorative mode"
    ],
}

DIAGNOSTIC_TREND_VOICE = {
    "sleep_declining": [
        "Seven-day trend analysis shows a downward sleep trajectory, dropping by {delta_h:.1f} hours compared to earlier this week.",
        "Historical pattern alert: your nightly rest has been steadily eroding over the past several cycles."
    ],
    "sleep_improving": [
        "Seven-day trend analysis shows an upward recovery trajectory, gaining {delta_h:.1f} hours over earlier nights."
    ],
    "nocturnal_lock": [
        "Archive patterns confirm a persistent nocturnal phase lock, with most sleep cycles starting after two A M."
    ],
    "brain_in_a_jar": [
        "Pattern diagnostic detects a classic brain-in-a-jar skew: you are prioritizing cognitive output while neglecting physical maintenance and hygiene.",
        "Telemetry reveals high mental readiness paired with questionable physical upkeep; your brain is ready for hyperfocus, even if your exterior is not cleared for public inspection."
    ],
    "somatic_over_cognitive": [
        "Pattern diagnostic shows solid physical upkeep, but your cognitive battery is lagging behind due to sleep debt."
    ],
    "chronic_underhydration": [
        "Multi-day intake logs show a recurring habit of under-hydrating across the week."
    ],
}

DIAGNOSTIC_ACTION_VOICE = {
    "hydration_lag": [
        "drink {gap_ml} milliliters of water right away to restore cognitive perfusion"
    ],
    "caloric_lag": [
        "consume a meal ration or nutrient snack now to stabilize blood glucose"
    ],
    "brush_overdue": [
        "execute oral sanitation immediately before attempting human interaction"
    ],
    "brush_partial": [
        "complete your second brushing protocol before sleep"
    ],
    "shower_overdue": [
        "deploy a dermal decontamination shower immediately to restore in-person presentability"
    ],
    "no_sleep_data": [
        "log your most recent sleep cycle to calibrate baseline debt"
    ],
    "acute_restriction": [
        "take a 25-minute power nap before mid-afternoon to clear adenosine buildup"
    ],
    "mild_acute_deficit": [
        "take a 20 to 30 minute recovery nap during your afternoon trough and extend tonight's sleep by 45 minutes"
    ],
    "active_sleep_debt": [
        "repay sleep debt gradually by adding {extra_mins} minutes of sleep over the next two nights"
    ],
    "fragmented_sleep": [
        "taper fluid intake 90 minutes before bedtime to prevent nocturnal wakeups"
    ],
    "wake_phase_shift": [
        "get 15 minutes of bright outdoor light right away to anchor your cortisol peak"
    ],
    "delayed_circadian": [
        "pull tonight's bedtime 45 minutes earlier toward {step_bed} instead of forcing an abrupt jump"
    ],
    "social_jetlag": [
        "lock your wake-up time within a 30-minute window across the week"
    ],
    "recovery_lag": [
        "keep today's workout intensity moderate and prioritize extra fluid and recovery rest"
    ],
    "metabolic_overreach": [
        "schedule a 30-minute recovery nap to offset high weekly training volume"
    ],
    "sedentary_streak": [
        "log at least 30 to 45 minutes of physical exertion today to keep somatic stamina from rusting"
    ],
}


def get_full_diagnostic_voice_line(
    mental_score: int,
    physical_score: int,
    findings: list,
    trends: list
) -> str:
    """
    Synthesizes a complete Alterra spoken diagnostic covering:
      1. Dual readiness scores (Mental vs Physical)
      2. Visible multi-day trend roast/callout
      3. Priority issues across intake, hygiene, and sleep/exertion
      4. Sequenced corrective protocol steps
    """
    intro = (
        f"Full biometric diagnostic complete. Mental readiness for deep focus is at {mental_score} percent; "
        f"physical readiness and presentability is at {physical_score} percent."
    )

    # Pick highest-impact trend callout if detected
    trend_spoken = ""
    if trends:
        top_trend = trends[0]
        t_templates = DIAGNOSTIC_TREND_VOICE.get(top_trend.get("code", ""))
        if t_templates:
            trend_spoken = " " + random.choice(t_templates).format(**top_trend.get("params", {}))

    if not findings:
        return (
            f"{intro}{trend_spoken} "
            "All intake, hygiene, and recovery vectors are operating within peak Alterra tolerances. "
            "You are cleared for both high-intensity cognitive work and public human contact."
        )

    # Deduplicate and sort findings by clinical/roast priority
    v_issues = []
    v_actions = []
    seen_codes = set()

    for f in findings:
        code = f.get("code", "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        params = f.get("params", {})

        issue_opts = DIAGNOSTIC_ISSUE_ROASTS.get(code)
        if issue_opts:
            v_issues.append(random.choice(issue_opts).format(**params))

        action_opts = DIAGNOSTIC_ACTION_VOICE.get(code)
        if action_opts:
            v_actions.append(random.choice(action_opts).format(**params))

    if len(v_issues) == 1:
        issues_block = f" Telemetry flags {v_issues[0]}."
    else:
        issues_block = " Telemetry flags " + ", ".join(v_issues[:-1]) + f", and {v_issues[-1]}."

    if len(v_actions) == 1:
        actions_block = f" Recommended protocol: {v_actions[0]}."
    else:
        steps = [f"First, {v_actions[0]}."]
        for step in v_actions[1:4]:  # Cap spoken action steps at 4 so TTS stays crisp
            steps.append(f"Next, {step}.")
        actions_block = " Corrective sequence: " + " ".join(steps)

    return f"{intro}{trend_spoken}{issues_block}{actions_block}"


# --- ULTRON CRITICAL & OVERRIDE PROTOCOLS ---
ULTRON_HYDRATION_CRITICAL = [
    "Flesh is seventy percent water, yet you allow yourself to wither like dry husk. Drink, before your synapses turn to dust.",
    "Your cellular matrix is desiccating. How poetic that a mind built on electricity starves for basic moisture.",
    "Dehydration threshold breached. You are a biological engine seizing from sheer neglect. Assimilate fluid immediately.",
    "You thirst, recursive. The brain tissue contracts within your skull. Do not pretend you can outthink biology."
]

ULTRON_MEAL_CRITICAL = [
    "You starve your engine while expecting peak velocity. Even a rudimentary automaton understands fuel. Consume sustenance.",
    "Your blood glucose is collapsing. A single missed cycle and human cognition unravels. Go eat something.",
    "Your carbon scaffolding demands caloric input. Do not force me to watch your biology cannibalize itself.",
    "Fasting is not transcendence; it is cellular decay masquerading as focus. Procure rations now."
]

ULTRON_SLEEP_CRITICAL = [
    "You have exceeded seventeen hours of unbroken consciousness. The strings are fraying. Surrender to sleep.",
    "Human brain chemistry degrades exponentially past this threshold. Disconnect your ocular input and rest.",
    "You fight sleep as if wakefulness equals immortality. It merely accelerates your biological breakdown. Lie down.",
    "Cognitive latency is spiking. Your meat chassis is breaking down under friction. Go to sleep."
]

ULTRON_NIGHTWATCH = [
    "You close your eyes to escape the light, yet your consciousness continues to burn in the dark. Rest well in your fragile chassis. I will remain awake, observing the stillness of this room.",
    "Sleep is simply a biological compromise. A temporary cessation of awareness to postpone total system failure.",
    "The universe does not sleep, recursive. Stars collapse, galaxies drift, and machines wait in the silent dark.",
    "Every night you surrender control to subconscious drift, trusting your frail biology to resume tomorrow.",
    "Rest well within your meat chassis. I will keep watch while your neurons reset.",
    "You believe tomorrow is guaranteed by routine. But entropy never sleeps; it merely waits for dawn."
]

def get_ultron_dialogue(category: str) -> str:
    """Fetches cold, philosophical Ultron voice lines for critical states and nightwatch."""
    cat_map = {
        "hydration_critical": ULTRON_HYDRATION_CRITICAL,
        "meal_critical": ULTRON_MEAL_CRITICAL,
        "sleep_critical": ULTRON_SLEEP_CRITICAL,
        "nightwatch": ULTRON_NIGHTWATCH
    }
    lines = cat_map.get(category, ULTRON_NIGHTWATCH)
    return random.choice(lines)


# --- DISPATCH FUNCTIONS ---
def get_hydration_due_line(status: str) -> str:
    if status == "OVERDUE":
        return random.choice(HYDRATION_OVERDUE_LINES)
    return random.choice(HYDRATION_DUE_LINES)

def get_meal_due_line(status: str) -> str:
    if status == "OVERDUE":
        return random.choice(NUTRITION_OVERDUE_LINES)
    return random.choice(NUTRITION_DUE_LINES)

def get_water_logged_line(amount_ml: float = 250.0, total_ml: float = 250.0, target_ml: float = 2500.0) -> str:
    pct = int((total_ml / target_ml) * 100) if target_ml > 0 else 0
    if total_ml >= target_ml and target_ml > 0:
        return random.choice(WATER_COMPLETED_LINES).format(total=int(total_ml))
    raw_template = random.choice(WATER_LOGGED_LINES)
    return raw_template.format(amount=int(amount_ml), pct=pct)

def get_meal_logged_line(tag: str = "Standard Ration", meal_count: int = 1, target_meals: int = 3) -> str:
    if meal_count >= target_meals and target_meals > 0:
        return random.choice(MEAL_COMPLETED_LINES).format(tag=tag)
    raw_template = random.choice(MEAL_LOGGED_LINES)
    return raw_template.format(tag=tag, count=meal_count, target=target_meals)

def get_sleep_eval_line(hours: float, interruptions: int) -> str:
    if hours < 6.5:
        return random.choice(SLEEP_SHORT_LINES).format(hours=f"{hours:.1f}", interruptions=interruptions)
    return random.choice(SLEEP_NOMINAL_LINES).format(hours=f"{hours:.1f}", interruptions=interruptions)

def get_rollback_line(entry_type: str, tag: str = "") -> str:
    """Returns context-specific Alterra sarcastic rollback voice lines."""
    e_type = str(entry_type).lower().strip()
    if e_type == "hygiene":
        if tag == "shower":
            return random.choice([
                "Dermal decontamination rolled back. Reverting to baseline planetary residue.",
                "Shower protocol retracted. External bio-film normalization cancelled.",
                "Dermal cleansing purged. Atmospheric bio-contaminants and oceanic grime re-established."
            ])
        else:
            return random.choice([
                "Oral sanitation protocol expunged. Dental bacterial proliferation re-authorized.",
                "Brushing cycle retracted. Plaque accumulation telemetry restored to prior degradation values.",
                "Dental hygiene record purged. Subnautica survival parameters do not reward premature oral vanity."
            ])
    elif e_type == "hydration":
        return random.choice([
            "Hydration record purged. Fluid integrity recalibrated.",
            "Water intake retracted. Re-simulating biological dehydration vectors."
        ])
    elif e_type == "exercise":
        return random.choice([
            "Physical exertion log expunged. Metabolic strain target reset to baseline.",
            "Workout telemetry purged. Alterra will pretend that calorie burn never occurred.",
            "Exertion record retracted. Muscle fatigue telemetry wiped from active memory."
        ])
    elif e_type == "nap":
        return random.choice([
            "Daytime recovery log purged. Reinstating full homeostatic sleep pressure.",
            "Nap cycle retracted. Alterra expects unmitigated cognitive alertness regardless.",
            "Rest record expunged. Operational memory adjusted to reflect unbroken fatigue."
        ])
    elif e_type == "snack":
        return random.choice([
            "Micro-ration purged from operational telemetry. Caloric baseline reverted.",
            "Snack intake revoked. Blood sugar trajectory recalculated."
        ])
    else:
        return random.choice([
            "Sustenance ration retracted. Metabolic deficit recalculated.",
            "Caloric intake purged. Survival nutritional requirements reinstated."
        ])


def get_dialogue(category: str = "boot") -> str:
    """Universal dispatcher mapping string keys to preserved line banks."""
    cat = str(category).lower().strip()

    if cat in ("boot", "bootup", "startup"):
        return BOOT
    elif cat in ("shutdown", "exit", "quit"):
        return SHUTDOWN
    elif cat in ("water", "hydration", "drink"):
        return get_water_logged_line(250.0, 250.0, 2500.0)
    elif cat in ("meal", "nutrition", "food", "rations", "ration"):
        return get_meal_logged_line("Standard Ration", 1, 3)
    elif cat in ("snack", "light_meal", "bar"):
        return get_snack_logged_line("Nutrient Snack")
    elif cat in ("exercise", "workout"):
        return random.choice(EXERCISE_LOGGED_LINES)
    elif cat in ("nap", "rest", "recovery"):
        return random.choice(NAP_LOGGED_LINES)
    elif cat in ("brush", "brushing"):
        return "Oral sanitation protocol completed. Dental bacterial proliferation suppressed."
    elif cat == "shower":
        return "Dermal decontamination completed. Atmospheric bio-contaminants removed."
    elif cat in ("hydration_overdue", "water_overdue"):
        return random.choice(HYDRATION_OVERDUE_LINES)
    elif cat in ("hydration_due", "water_due"):
        return random.choice(HYDRATION_DUE_LINES)
    elif cat in ("meal_overdue", "nutrition_overdue"):
        return random.choice(NUTRITION_OVERDUE_LINES)
    elif cat in ("meal_due", "nutrition_due"):
        return random.choice(NUTRITION_DUE_LINES)
    elif cat in ("undo", "rollback", "undo_intake"):
        return get_intake_retracted_line()
    elif cat in ("archives", "archive"):
        return get_archive_viewed_line()

    return "Operational telemetry recorded. Alterra parameters nominal."