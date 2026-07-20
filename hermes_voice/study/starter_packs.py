"""Curated starter decks for Hermes Study."""

from __future__ import annotations

from typing import TypedDict

from hermes_voice.study.store import StudyStore


class StarterCard(TypedDict):
    question: str
    answer: str
    notes: str


class StarterDeck(TypedDict):
    name: str
    description: str
    cards: tuple[StarterCard, ...]


MCAT_FOUNDATIONS: tuple[StarterDeck, ...] = (
    {
        "name": "MCAT Biology: Cells, Genetics & Organ Systems",
        "description": (
            "High-yield cellular biology, genetics, physiology, and organ-system "
            "relationships for Biological and Biochemical Foundations."
        ),
        "cards": (
            {
                "question": (
                    "How do simple diffusion, facilitated diffusion, and active "
                    "transport differ?"
                ),
                "answer": (
                    "Simple and facilitated diffusion move substances down an "
                    "electrochemical gradient without direct energy input; facilitated "
                    "diffusion uses a membrane protein. Active transport moves a solute "
                    "against its gradient and requires energy."
                ),
                "notes": (
                    "Primary active transport directly uses ATP, while secondary active "
                    "transport uses a gradient created by another transporter. MCAT trap: "
                    "a protein-mediated process is not automatically active transport."
                ),
            },
            {
                "question": "What is the purpose of the G1, G2, and spindle checkpoints?",
                "answer": (
                    "G1 checks cell size, nutrients, growth signals, and DNA damage; G2 "
                    "checks DNA replication and damage; the spindle checkpoint confirms "
                    "that every chromosome is correctly attached before anaphase."
                ),
                "notes": (
                    "Checkpoint failure permits mutation propagation or aneuploidy. "
                    "Remember: p53 can pause the cycle or promote apoptosis when DNA "
                    "damage cannot be repaired."
                ),
            },
            {
                "question": (
                    "When does Mendel's law of independent assortment fail to predict "
                    "offspring ratios?"
                ),
                "answer": (
                    "It can fail when genes are linked on the same chromosome, especially "
                    "when they are close enough that crossing over rarely separates them."
                ),
                "notes": (
                    "Recombination frequency increases with distance between loci and "
                    "approaches 50 percent for genes that behave as unlinked. A measured "
                    "frequency below 50 percent suggests linkage."
                ),
            },
            {
                "question": "What ionic events create a neuronal action potential?",
                "answer": (
                    "Threshold opens voltage-gated sodium channels, causing rapid sodium "
                    "influx and depolarization. Sodium channels then inactivate while "
                    "voltage-gated potassium channels open, causing potassium efflux and "
                    "repolarization, often followed by brief hyperpolarization."
                ),
                "notes": (
                    "The sodium-potassium ATPase maintains long-term gradients but does not "
                    "directly create the rapid upstroke. The absolute refractory period is "
                    "mainly due to sodium-channel inactivation."
                ),
            },
            {
                "question": (
                    "How does antidiuretic hormone increase water reabsorption in the kidney?"
                ),
                "answer": (
                    "ADH binds V2 receptors on collecting-duct principal cells, activating "
                    "a cAMP pathway that inserts aquaporin-2 channels into the apical "
                    "membrane, increasing water reabsorption."
                ),
                "notes": (
                    "Water then exits basolaterally through other aquaporins. The effect "
                    "depends on the medullary osmotic gradient established by the loop of "
                    "Henle and urea recycling."
                ),
            },
        ),
    },
    {
        "name": "MCAT Biochemistry: Amino Acids, Enzymes & Metabolism",
        "description": (
            "Amino-acid chemistry, enzyme behavior, bioenergetics, and central metabolism."
        ),
        "cards": (
            {
                "question": (
                    "How can you predict whether an ionizable group is mostly protonated "
                    "or deprotonated?"
                ),
                "answer": (
                    "Compare pH with pKa. When pH is below pKa, the protonated form "
                    "predominates; when pH is above pKa, the deprotonated form predominates."
                ),
                "notes": (
                    "At pH equal to pKa, the two forms are present at equal concentrations. "
                    "MCAT trap: protonation does not always mean a positive charge; a "
                    "protonated carboxyl group is neutral."
                ),
            },
            {
                "question": (
                    "How does a competitive inhibitor change apparent Km and Vmax?"
                ),
                "answer": (
                    "It increases apparent Km because more substrate is needed to reach half "
                    "Vmax, while Vmax remains unchanged because sufficiently high substrate "
                    "concentration can outcompete the inhibitor."
                ),
                "notes": (
                    "On a Lineweaver-Burk plot, the y-intercept is unchanged and the slope "
                    "increases. Contrast with pure noncompetitive inhibition, which lowers "
                    "Vmax without changing Km."
                ),
            },
            {
                "question": "What are the net products of glycolysis per glucose molecule?",
                "answer": (
                    "Two pyruvate, two net ATP, two NADH, and two water molecules."
                ),
                "notes": (
                    "Glycolysis invests two ATP and later produces four. Under anaerobic "
                    "conditions, fermentation regenerates NAD+ so glycolysis can continue; "
                    "it does not add more net ATP beyond glycolysis."
                ),
            },
            {
                "question": "Why is oxygen required for sustained oxidative phosphorylation?",
                "answer": (
                    "Oxygen is the terminal electron acceptor at complex IV. It accepts "
                    "electrons and protons to form water, allowing electron flow and proton "
                    "pumping to continue."
                ),
                "notes": (
                    "Without oxygen, the electron transport chain backs up, NADH cannot be "
                    "efficiently reoxidized, and the proton gradient collapses. ATP synthase "
                    "depends on that gradient rather than directly using oxygen."
                ),
            },
            {
                "question": "What does beta oxidation remove from a fatty acid during each cycle?",
                "answer": (
                    "Each cycle removes a two-carbon acetyl-CoA unit and generally produces "
                    "one FADH2 and one NADH while shortening the fatty acyl chain by two carbons."
                ),
                "notes": (
                    "Long-chain fatty acids enter mitochondria through the carnitine shuttle. "
                    "Odd-chain fatty acids eventually yield propionyl-CoA, which can become "
                    "succinyl-CoA and contribute to gluconeogenesis."
                ),
            },
        ),
    },
    {
        "name": "MCAT General & Organic Chemistry",
        "description": (
            "Equilibrium, acids and bases, thermodynamics, redox chemistry, separations, "
            "and organic reaction patterns."
        ),
        "cards": (
            {
                "question": "How does a system at equilibrium respond to an imposed change?",
                "answer": (
                    "By Le Chatelier's principle, the system shifts in the direction that "
                    "partly opposes the change in concentration, pressure, volume, or temperature."
                ),
                "notes": (
                    "A catalyst speeds both forward and reverse reactions and does not change "
                    "the equilibrium constant or equilibrium composition. Only temperature "
                    "changes the equilibrium constant for a given reaction."
                ),
            },
            {
                "question": "When is a buffer most effective?",
                "answer": (
                    "A buffer is most effective when the weak acid and conjugate base have "
                    "similar concentrations, so pH is near the acid's pKa."
                ),
                "notes": (
                    "The useful range is roughly pKa plus or minus one pH unit. Buffer capacity "
                    "also increases with the total concentration of the conjugate pair."
                ),
            },
            {
                "question": "What conditions favor an SN2 reaction over an SN1 reaction?",
                "answer": (
                    "SN2 is favored by an unhindered methyl or primary substrate, a strong "
                    "nucleophile, and a polar aprotic solvent. It occurs in one concerted step "
                    "with inversion of configuration."
                ),
                "notes": (
                    "SN1 is favored by stable carbocations, often tertiary substrates, and "
                    "polar protic solvents. MCAT trap: a strong bulky base may favor elimination "
                    "rather than substitution."
                ),
            },
            {
                "question": "How can oxidation and reduction be recognized in an organic molecule?",
                "answer": (
                    "Oxidation generally increases bonds from carbon to electronegative atoms "
                    "or decreases carbon-hydrogen bonds; reduction does the opposite."
                ),
                "notes": (
                    "Electron bookkeeping and oxidation states remain the formal standard. "
                    "Common sequence: primary alcohol to aldehyde to carboxylic acid is progressive "
                    "oxidation."
                ),
            },
            {
                "question": "How does normal-phase silica chromatography separate compounds?",
                "answer": (
                    "The stationary phase is polar, so more polar compounds interact more strongly "
                    "and move or elute more slowly; less polar compounds travel farther or elute first."
                ),
                "notes": (
                    "Reverse-phase chromatography reverses this pattern because its stationary "
                    "phase is nonpolar. In thin-layer chromatography, a larger Rf means greater "
                    "movement with the solvent front."
                ),
            },
        ),
    },
    {
        "name": "MCAT Physics: Mechanics, Fluids, Circuits & Optics",
        "description": (
            "Equation-centered physics with conceptual checks and common proportional reasoning."
        ),
        "cards": (
            {
                "question": "How do equivalent resistance rules differ for series and parallel resistors?",
                "answer": (
                    "Series resistances add directly and carry the same current. Parallel branches "
                    "share the same voltage and satisfy one over Req equals the sum of one over each resistance."
                ),
                "notes": (
                    "Adding a series resistor raises total resistance; adding a parallel branch lowers "
                    "total resistance. For two parallel resistors, Req must be smaller than either one."
                ),
            },
            {
                "question": "What does the continuity equation imply for fluid speed in a narrowing pipe?",
                "answer": (
                    "For steady incompressible flow, area times speed is constant, so fluid speed "
                    "increases as cross-sectional area decreases."
                ),
                "notes": (
                    "Under ideal horizontal flow, Bernoulli's equation then predicts lower static "
                    "pressure where speed is higher. Do not apply this blindly to viscous or turbulent flow."
                ),
            },
            {
                "question": "What is the work-energy theorem?",
                "answer": "The net work done on an object equals its change in kinetic energy.",
                "notes": (
                    "Work by a constant force is force times displacement times the cosine of the angle "
                    "between them. A perpendicular force, such as ideal centripetal force, does no work."
                ),
            },
            {
                "question": "How does electrostatic force change if the distance between two charges doubles?",
                "answer": "Its magnitude becomes one fourth as large, because Coulomb force varies as one over distance squared.",
                "notes": (
                    "Electric field follows the same inverse-square distance dependence for a point charge. "
                    "Electric potential varies as one over distance, not one over distance squared."
                ),
            },
            {
                "question": "What image does a converging lens form when the object is beyond the focal point?",
                "answer": (
                    "It forms a real, inverted image on the opposite side of the lens. Image size depends "
                    "on whether the object is beyond, at, or between one and two focal lengths."
                ),
                "notes": (
                    "When the object is inside the focal length, the image is virtual, upright, and magnified. "
                    "Use principal rays and the sign convention rather than memorizing only one case."
                ),
            },
        ),
    },
    {
        "name": "MCAT Psychology & Sociology",
        "description": (
            "Learning, cognition, development, research methods, social structure, and inequality."
        ),
        "cards": (
            {
                "question": "What is the key difference between classical and operant conditioning?",
                "answer": (
                    "Classical conditioning learns an association between stimuli and produces an elicited "
                    "response; operant conditioning learns an association between behavior and consequence."
                ),
                "notes": (
                    "In operant conditioning, reinforcement increases behavior and punishment decreases it. "
                    "Positive means adding a stimulus; negative means removing one."
                ),
            },
            {
                "question": "How do positive reinforcement and negative reinforcement differ?",
                "answer": (
                    "Both increase a behavior. Positive reinforcement adds a desirable stimulus, while negative "
                    "reinforcement removes an aversive stimulus after the behavior."
                ),
                "notes": (
                    "Negative reinforcement is not punishment. The fastest classification method is first ask "
                    "whether behavior increases or decreases, then ask whether something is added or removed."
                ),
            },
            {
                "question": "What cognitive ability marks Piaget's formal operational stage?",
                "answer": (
                    "The ability to reason abstractly and hypothetically, including systematic testing of possibilities."
                ),
                "notes": (
                    "Concrete operational thinking supports conservation and logical operations on tangible objects. "
                    "Formal operations extend reasoning to abstract propositions."
                ),
            },
            {
                "question": "What is the difference between role conflict and role strain?",
                "answer": (
                    "Role conflict occurs when expectations from different social roles clash; role strain is tension "
                    "among competing demands within a single role."
                ),
                "notes": (
                    "Example of conflict: employee duties interfere with parenting duties. Example of strain: one "
                    "employee role contains incompatible demands from a manager and clients."
                ),
            },
            {
                "question": "How does a confounding variable threaten a causal conclusion?",
                "answer": (
                    "It is associated with both the proposed cause and the outcome, providing an alternative explanation "
                    "for the observed relationship."
                ),
                "notes": (
                    "Random assignment helps distribute confounders across experimental groups. Random sampling instead "
                    "primarily improves population representativeness and external validity."
                ),
            },
        ),
    },
    {
        "name": "MCAT CARS: Passage Reasoning",
        "description": (
            "Repeatable reasoning habits for main idea, tone, inference, evidence, and answer elimination."
        ),
        "cards": (
            {
                "question": "What should a strong CARS main-idea statement contain?",
                "answer": (
                    "The author's central claim or purpose, the major subject, and the author's overall direction or stance."
                ),
                "notes": (
                    "It should be broad enough to cover the whole passage but specific enough to exclude nearby topics. "
                    "A memorable detail is rarely the main idea unless the author builds the passage around it."
                ),
            },
            {
                "question": "How should an inference question be answered in CARS?",
                "answer": (
                    "Choose the conclusion most strongly supported by the passage, even when it is not stated word for word."
                ),
                "notes": (
                    "A valid inference requires a short evidence chain from the text. Reject answers that are merely plausible "
                    "in real life but require assumptions the author never supplied."
                ),
            },
            {
                "question": "When should outside knowledge be used in a CARS passage?",
                "answer": "It generally should not be used; treat the passage as the controlling evidence and worldview.",
                "notes": (
                    "Even accurate outside facts can lead to a wrong answer if they conflict with the author's argument. "
                    "Use background knowledge only to understand ordinary language, not to replace textual evidence."
                ),
            },
            {
                "question": "What is the purpose of a brief passage map?",
                "answer": (
                    "To record each paragraph's function and track shifts in claim, evidence, examples, objections, and tone."
                ),
                "notes": (
                    "Map function rather than copying details. Useful labels include introduces problem, gives example, presents "
                    "counterargument, and states author's resolution."
                ),
            },
            {
                "question": "What answer-choice features often signal a CARS trap?",
                "answer": (
                    "Extreme wording, a true but irrelevant detail, reversed logic, unsupported scope expansion, or language that "
                    "answers a different question."
                ),
                "notes": (
                    "Do not reject every strong word automatically; reject it when the passage does not justify that strength. "
                    "Compare each choice with the author's exact scope and attitude."
                ),
            },
        ),
    },
)


def install_mcat_foundations(store: StudyStore) -> dict[str, int]:
    """Install missing decks/cards without duplicating an existing question."""
    decks_created = 0
    cards_created = 0
    cards_skipped = 0

    for pack_deck in MCAT_FOUNDATIONS:
        deck = store.find_deck(pack_deck["name"])
        if deck is None:
            deck = store.create_deck(
                pack_deck["name"],
                pack_deck["description"],
            )
            decks_created += 1
        existing = {
            str(card["question"]).strip().casefold()
            for card in store.list_cards(int(deck["id"]))
        }
        for pack_card in pack_deck["cards"]:
            key = pack_card["question"].strip().casefold()
            if key in existing:
                cards_skipped += 1
                continue
            store.create_card(
                int(deck["id"]),
                question=pack_card["question"],
                answer=pack_card["answer"],
                notes=pack_card["notes"],
            )
            existing.add(key)
            cards_created += 1

    return {
        "decks_created": decks_created,
        "cards_created": cards_created,
        "cards_skipped": cards_skipped,
    }
