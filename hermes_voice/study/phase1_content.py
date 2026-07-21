"""Versioned MCAT Medical Foundations Phase 1 teaching content.

The pack is intentionally generated from readable, reviewed concept records. Each
course contains five core concepts, and each concept produces six complementary
cards: recall, mechanism, application, comparison, prediction, and misconception.
"""

from __future__ import annotations

import base64
import binascii
import struct
import zlib
from typing import NamedTuple

from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.store import StudyConflictError, StudyStore

PACK_KEY = "mcat-phase-1-v1"
CURRICULUM_KEY = "mcat-medical-foundations-phase-1"


class Concept(NamedTuple):
    name: str
    explanation: str
    application: str
    trap: str


class Course(NamedTuple):
    key: str
    name: str
    concepts: tuple[Concept, ...]


def _c(name: str, explanation: str, application: str, trap: str) -> Concept:
    return Concept(name, explanation, application, trap)


COURSES: tuple[Course, ...] = (
    Course("foundation-00-core", "00 Learning and Scientific Reasoning", (
        _c("active recall", "retrieving an idea from memory before checking the answer strengthens access to that idea", "answer a question aloud, then compare the response with the explanation", "rereading can feel fluent without proving that the information can be retrieved"),
        _c("spaced practice", "reviewing material across separated sessions improves durable retention", "schedule difficult cards sooner and mastered cards later", "cramming increases short-term familiarity but usually produces rapid forgetting"),
        _c("independent and dependent variables", "the independent variable is manipulated and the dependent variable is measured", "identify what the investigator changes and what outcome responds", "a measured variable is not automatically the independent variable"),
        _c("controls and confounders", "controls isolate the tested factor while confounders vary with it and offer alternative explanations", "compare experimental groups with an appropriate negative or positive control", "correlation alone cannot exclude a third-variable explanation"),
        _c("graph interpretation", "axes, units, uncertainty, and trend shape determine what a graph supports", "state the direction, magnitude, and limits of a relationship before explaining it", "extrapolating beyond the measured range can produce unsupported conclusions"),
    )),
    Course("foundation-01-core", "01 Matter, Measurement, and Units", (
        _c("dimensional analysis", "units can be multiplied and canceled like algebraic factors", "construct conversion factors so unwanted units cancel", "using a numerically correct factor upside down gives the wrong unit and magnitude"),
        _c("scientific notation", "powers of ten separate scale from significant digits", "combine exponents before estimating the coefficient", "moving the decimal requires the opposite change in exponent"),
        _c("significant figures", "reported precision reflects the least precise measured input", "round multiplication by significant figures and addition by decimal place", "exact counted quantities do not limit significant figures"),
        _c("density", "density is mass per unit volume and is an intensive property", "predict floating or sinking by comparing object and fluid densities", "a larger object can have more mass without having greater density"),
        _c("moles and molar mass", "one mole connects particle count with measurable mass", "convert grams to moles before using stoichiometric ratios", "coefficients relate moles, not grams directly"),
    )),
    Course("foundation-02-core", "02 Atomic Structure", (
        _c("protons neutrons and electrons", "protons set atomic identity, neutrons change isotope, and electrons determine charge", "find each count from atomic number, mass number, and ionic charge", "mass number is not the same as average atomic mass"),
        _c("electron configuration", "electrons fill orbitals according to energy, exclusion, and Hund's rule", "use valence configuration to predict bonding and ion formation", "removing electrons follows occupied energy order rather than simple written order"),
        _c("periodic trends", "effective nuclear charge and shell distance shape radius and ionization energy", "compare atoms by position while accounting for charge", "a cation is usually smaller than its neutral atom, while an anion is larger"),
        _c("isotopes", "isotopes share proton number but differ in neutron number", "calculate weighted average atomic mass from abundance", "chemical behavior is similar, but nuclear stability and mass can differ"),
        _c("photons and spectra", "electronic transitions absorb or emit photons whose energy matches the level difference", "relate wavelength, frequency, and energy", "longer wavelength means lower frequency and lower photon energy"),
    )),
    Course("foundation-03-core", "03 Chemical Bonds and Reactions", (
        _c("ionic and covalent bonding", "ionic bonding emphasizes electrostatic attraction while covalent bonding shares electron density", "predict bonding from electronegativity and structure", "bonding exists on a continuum rather than in perfectly separate categories"),
        _c("Lewis structures and formal charge", "Lewis structures track valence electrons and formal charge helps select plausible arrangements", "count electrons, satisfy octets when appropriate, and minimize charge separation", "second-period elements cannot normally exceed an octet"),
        _c("molecular geometry", "electron-domain repulsion determines geometry and bond angles", "use VSEPR to predict shape and polarity", "lone pairs occupy domains and compress adjacent bond angles"),
        _c("intermolecular forces", "dispersion, dipole interactions, and hydrogen bonding influence physical properties", "compare boiling points using force strength and molecular size", "hydrogen bonding requires hydrogen attached to nitrogen, oxygen, or fluorine"),
        _c("reaction stoichiometry", "balanced coefficients conserve atoms and give mole ratios", "identify the limiting reagent before calculating product", "the reagent with fewer grams is not necessarily limiting"),
    )),
    Course("foundation-04-core", "04 Water, Solutions, Acids, Bases, and Buffers", (
        _c("water polarity", "water's bent geometry and polar bonds create a net dipole", "explain solvation of ions and polar molecules", "hydrophobic substances aggregate because of water's organization, not because they strongly attract each other"),
        _c("molarity and dilution", "molarity is moles of solute per liter of solution", "use conservation of solute for dilution calculations", "adding solvent changes concentration but not solute moles"),
        _c("pH and pKa", "pH measures proton activity and pKa describes acid strength", "compare pH with pKa to determine the dominant protonation state", "protonated does not always mean positively charged"),
        _c("buffers", "a weak acid and conjugate base resist pH change by consuming added acid or base", "use Henderson-Hasselbalch near the pKa", "buffers have finite capacity and fail after one component is depleted"),
        _c("solubility and precipitation", "dissolution competes with lattice formation and is summarized by equilibrium constants", "compare an ion product with Ksp to predict precipitation", "a small Ksp does not by itself specify molar solubility without stoichiometry"),
    )),
    Course("foundation-05-core", "05 Cell Structure and Membranes", (
        _c("prokaryotic and eukaryotic cells", "eukaryotes compartmentalize functions in membrane-bound organelles", "identify which processes occur in nucleus, cytosol, or organelles", "prokaryotes still contain membranes, ribosomes, DNA, and metabolic pathways"),
        _c("organelle function", "organelles divide biosynthesis, energy conversion, trafficking, and degradation", "trace a secreted protein through rough ER, Golgi, vesicle, and membrane", "free and bound ribosomes are structurally similar but translate proteins with different destinations"),
        _c("membrane structure", "a fluid phospholipid bilayer contains proteins, cholesterol, and carbohydrates", "predict how lipid saturation and temperature affect fluidity", "cholesterol buffers fluidity rather than always increasing or decreasing it"),
        _c("membrane transport", "passive transport follows electrochemical gradients while active transport uses energy", "distinguish channels, carriers, pumps, symporters, and antiporters", "protein-mediated transport is not automatically active"),
        _c("osmosis and tonicity", "water moves toward greater effective solute concentration across a permeable membrane", "predict cell volume in hypo-, iso-, and hypertonic solutions", "osmolarity counts particles, while tonicity depends on nonpenetrating solutes"),
    )),
    Course("foundation-06-core", "06 Biological Molecules", (
        _c("amino acids", "amino-acid side chains determine charge, polarity, and chemical behavior", "classify residues and predict interactions in proteins", "side-chain charge depends on pH relative to pKa"),
        _c("protein structure", "primary sequence supports secondary, tertiary, and quaternary organization", "identify interactions disrupted by heat, pH, or reducing agents", "denaturation usually disrupts higher structure without hydrolyzing peptide bonds"),
        _c("carbohydrates", "monosaccharides form glycosidic bonds and serve energy and structural roles", "distinguish reducing sugars and common polysaccharides", "alpha and beta linkages can produce very different biological properties"),
        _c("lipids", "fatty acids, triacylglycerols, phospholipids, and steroids have distinct roles", "relate saturation to packing and membrane behavior", "lipids are grouped by hydrophobicity rather than a single repeating monomer"),
        _c("nucleotides", "nucleotides contain base, sugar, and phosphate and support information and energy transfer", "distinguish nucleosides from nucleotides and purines from pyrimidines", "ATP is both an energy-coupling molecule and a nucleotide"),
    )),
    Course("foundation-07-core", "07 DNA, RNA, and Protein Synthesis", (
        _c("DNA replication", "semiconservative replication uses complementary templates and synthesis proceeds five-prime to three-prime", "distinguish leading and lagging strand synthesis", "DNA polymerase extends an existing primer and does not begin synthesis de novo"),
        _c("transcription", "RNA polymerase uses a DNA template to make RNA", "identify template versus coding strands and promoter direction", "the RNA sequence matches the coding strand except uracil replaces thymine"),
        _c("RNA processing", "eukaryotic transcripts receive a cap, poly-A tail, and splicing", "predict how alternative splicing changes protein products", "introns are removed from RNA, not deleted from genomic DNA"),
        _c("translation", "ribosomes read mRNA codons and tRNAs deliver amino acids", "follow initiation, elongation, termination, and reading frame", "the anticodon pairs antiparallel with the codon"),
        _c("mutation effects", "substitutions and insertions can be silent, missense, nonsense, or frameshifting", "predict protein consequences from codon and reading-frame changes", "a DNA mutation outside coding sequence can still alter expression"),
    )),
    Course("foundation-08-core", "08 Enzymes, ATP, and Metabolism", (
        _c("enzyme catalysis", "enzymes lower activation energy without changing reaction free energy or equilibrium", "interpret reaction-coordinate diagrams", "enzymes accelerate forward and reverse reactions"),
        _c("Michaelis-Menten behavior", "Km reflects the substrate concentration at half Vmax in the simple model", "compare affinity and catalytic capacity from curves", "a lower Km often suggests higher apparent affinity but does not equal binding energy in every mechanism"),
        _c("enzyme inhibition", "competitive, noncompetitive, uncompetitive, and mixed inhibitors alter Km and Vmax differently", "identify inhibition patterns from kinetic data", "high substrate can overcome competitive inhibition but not restore every inhibited Vmax"),
        _c("ATP coupling", "ATP hydrolysis can drive unfavorable processes through a shared intermediate", "sum coupled free-energy changes", "ATP does not make every reaction favorable unless coupling is mechanistically linked"),
        _c("central metabolism", "glycolysis, the citric acid cycle, and oxidative phosphorylation transfer energy to ATP and reduced carriers", "track carbon, ATP, NADH, and oxygen roles", "oxygen is the terminal electron acceptor, not a direct substrate of glycolysis"),
    )),
    Course("foundation-09-core", "09 Cell Cycle, Mitosis, and Meiosis", (
        _c("cell-cycle phases", "G1, S, G2, and M coordinate growth, replication, and division", "place replication and chromosome states in the correct phase", "chromosome number and chromatid number are not interchangeable"),
        _c("cell-cycle checkpoints", "checkpoints monitor damage, replication, and spindle attachment", "predict consequences of checkpoint failure", "cyclins fluctuate while many cyclin-dependent kinases remain present"),
        _c("mitosis", "mitosis separates sister chromatids to form genetically similar daughter nuclei", "order prophase through telophase and cytokinesis", "homologous chromosomes do not pair as tetrads in mitosis"),
        _c("meiosis", "two divisions reduce ploidy and generate genetic diversity", "distinguish homolog separation in meiosis I from chromatid separation in meiosis II", "DNA replicates once before meiosis, not between the two divisions"),
        _c("recombination and independent assortment", "crossing over and random homolog orientation generate new allele combinations", "relate linkage distance to recombination frequency", "recombination frequency cannot exceed fifty percent"),
    )),
    Course("foundation-10-core", "10 Genetics and Inheritance", (
        _c("Mendelian segregation", "allele pairs separate during gamete formation", "calculate monohybrid probabilities", "dominant describes phenotype expression, not population frequency or fitness"),
        _c("independent assortment", "unlinked allele pairs assort independently", "multiply probabilities for independent events", "linked genes can violate expected independent ratios"),
        _c("pedigrees", "pedigree patterns can indicate autosomal, sex-linked, dominant, or recessive inheritance", "use affected status and transmission to constrain genotypes", "small pedigrees may fit more than one model without additional evidence"),
        _c("Hardy-Weinberg equilibrium", "allele and genotype frequencies remain stable under ideal assumptions", "use p plus q equals one and p-squared plus two-pq plus q-squared equals one", "the frequency of a recessive phenotype is q-squared, not q"),
        _c("gene-environment interaction", "phenotype reflects genotype, environment, and their interaction", "interpret heritability and reaction norms", "high heritability does not mean a trait is fixed or unaffected by environment"),
    )),
    Course("foundation-11-core", "11 Tissues, Homeostasis, and Organ Systems", (
        _c("epithelial tissue", "epithelia form barriers and specialized exchange surfaces", "relate cell shape and layering to diffusion, protection, or secretion", "vascular supply generally reaches epithelia by diffusion from underlying tissue"),
        _c("connective tissue", "cells embedded in extracellular matrix provide support, storage, transport, and defense", "compare bone, cartilage, blood, and adipose tissue", "blood is classified as connective tissue despite its fluid matrix"),
        _c("muscle tissue", "skeletal, cardiac, and smooth muscle differ in control, structure, and function", "connect calcium signaling with contraction", "cardiac muscle is striated but involuntary"),
        _c("nervous tissue", "neurons transmit signals while glia support, insulate, and regulate", "distinguish sensory input, integration, and motor output", "glial cells are active participants rather than passive filler"),
        _c("homeostatic feedback", "negative feedback opposes deviations while positive feedback amplifies a process to an endpoint", "identify sensor, integrator, and effector", "positive feedback is not inherently harmful; childbirth and clotting use it productively"),
    )),
    Course("foundation-12-core", "12 Nervous and Endocrine Foundations", (
        _c("resting membrane potential", "ion gradients and selective permeability create a negative resting potential", "predict effects of changing potassium permeability", "the sodium-potassium pump maintains gradients but is not the sole immediate cause of voltage"),
        _c("action potentials", "voltage-gated sodium and potassium channels produce depolarization and repolarization", "map channel states to refractory periods", "action-potential amplitude does not encode stimulus strength"),
        _c("synaptic transmission", "neurotransmitter release converts an electrical signal into chemical communication", "predict effects of receptor agonists, antagonists, and reuptake inhibitors", "an excitatory transmitter can have different effects depending on its receptor"),
        _c("hormone classes", "peptide and catecholamine hormones use membrane receptors while many steroids use intracellular receptors", "predict onset, duration, and signaling pathway", "thyroid hormone is amino-acid-derived but acts through nuclear receptors"),
        _c("endocrine feedback", "hypothalamic, pituitary, and target-gland hormones often form negative-feedback axes", "localize a defect from upstream and downstream hormone levels", "a high trophic hormone with low target hormone suggests primary target-gland failure"),
    )),
    Course("foundation-13-core", "13 Cardiovascular and Respiratory Foundations", (
        _c("cardiac blood flow", "right heart sends blood to lungs and left heart sends blood to systemic tissues", "trace a red blood cell through chambers, valves, and vessels", "arteries and veins are defined by direction of flow, not oxygen content"),
        _c("cardiac cycle", "pressure differences open and close valves during filling and ejection", "relate heart sounds to valve closure", "valves open passively because of pressure gradients"),
        _c("blood pressure and flow", "flow depends on pressure difference and resistance", "apply radius effects to vascular resistance", "small radius changes strongly affect resistance because of the fourth-power relationship"),
        _c("gas exchange", "oxygen and carbon dioxide diffuse down partial-pressure gradients", "predict effects of surface area, thickness, and ventilation-perfusion mismatch", "total gas concentration and partial pressure are related but not identical"),
        _c("hemoglobin binding", "cooperative binding gives hemoglobin a sigmoidal oxygen-dissociation curve", "interpret right and left shifts", "a right shift lowers affinity and promotes tissue unloading"),
    )),
    Course("foundation-14-core", "14 Digestive, Renal, and Fluid Foundations", (
        _c("digestive organization", "mechanical and chemical digestion prepare nutrients for absorption", "match organs with enzymes, secretions, and absorbed products", "most nutrient absorption occurs in the small intestine, not the stomach"),
        _c("liver and pancreas", "the liver processes portal blood while the pancreas supplies digestive enzymes and bicarbonate", "predict effects of bile or pancreatic insufficiency", "bile emulsifies fat but is not itself a digestive enzyme"),
        _c("nephron filtration", "glomerular pressure filters plasma while retaining cells and most proteins", "distinguish filtration, reabsorption, secretion, and excretion", "a filtered substance is not necessarily excreted"),
        _c("countercurrent multiplication", "the loop of Henle establishes a medullary osmotic gradient", "explain how ADH uses the gradient to conserve water", "ADH increases collecting-duct water permeability but does not create the gradient alone"),
        _c("fluid compartments", "water shifts among plasma, interstitial fluid, and cells according to osmotic forces", "predict edema and cell-volume changes", "isotonic volume expansion changes extracellular volume without directly changing cell volume"),
    )),
    Course("foundation-15-core", "15 Immune and Reproductive Foundations", (
        _c("innate immunity", "barriers, phagocytes, complement, and inflammation provide rapid nonspecific defense", "identify early responses to tissue injury or infection", "innate immunity can recognize conserved patterns and is not completely nonspecific"),
        _c("adaptive immunity", "B and T lymphocytes provide antigen-specific responses and memory", "distinguish humoral and cell-mediated immunity", "antibodies are secreted by plasma cells derived from B cells"),
        _c("antigen presentation", "MHC molecules display peptides to T cells", "compare MHC I with cytotoxic T cells and MHC II with helper T cells", "mature red blood cells lack nuclei and do not use normal MHC I presentation"),
        _c("reproductive hormones", "hypothalamic, pituitary, and gonadal hormones coordinate gamete production and cycles", "track FSH, LH, estrogen, progesterone, and testosterone feedback", "the LH surge is a positive-feedback event within an otherwise feedback-regulated cycle"),
        _c("fertilization and development", "fertilization restores diploidy and early cleavage produces a blastocyst", "order implantation and germ-layer formation", "cleavage increases cell number without large growth in total embryo size"),
    )),
    Course("foundation-16-core", "16 Motion, Forces, Work, and Energy", (
        _c("kinematics", "position, velocity, and acceleration describe motion with distinct meanings", "interpret slopes and areas on motion graphs", "zero velocity at an instant does not require zero acceleration"),
        _c("Newton's laws", "net force changes motion and interaction forces occur in equal opposite pairs", "draw a free-body diagram before writing equations", "action-reaction forces act on different objects and do not cancel on one diagram"),
        _c("work and energy", "net work changes kinetic energy while conservative forces exchange kinetic and potential energy", "choose energy methods when path details are unnecessary", "a force perpendicular to displacement does no mechanical work"),
        _c("momentum and impulse", "impulse changes momentum and momentum is conserved in isolated systems", "analyze collisions and force-time graphs", "kinetic energy is conserved only in elastic collisions"),
        _c("rotation and torque", "torque depends on force and perpendicular lever arm", "apply rotational equilibrium and angular analogies", "a large force through the pivot produces zero torque about that pivot"),
    )),
    Course("foundation-17-core", "17 Fluids, Pressure, and Circulation Physics", (
        _c("hydrostatic pressure", "pressure in a static fluid increases with depth and density", "compare pressures using rho-g-h", "container shape does not change pressure at the same depth"),
        _c("buoyancy", "buoyant force equals the weight of displaced fluid", "predict floating fraction from density", "a floating object displaces its own weight, not necessarily its full volume"),
        _c("continuity", "steady incompressible flow conserves volume rate", "relate area and speed in changing vessel diameter", "continuity alone does not determine pressure"),
        _c("Bernoulli principle", "ideal flow trades pressure, kinetic, and gravitational energy per volume", "compare speed and pressure along a streamline", "viscosity and turbulence limit direct Bernoulli application"),
        _c("Poiseuille flow", "laminar resistance rises with viscosity and length and falls strongly with radius", "explain vascular resistance changes", "doubling radius changes flow by a factor of sixteen when other terms stay constant"),
    )),
    Course("foundation-18-core", "18 Electricity, Waves, Sound, and Optics", (
        _c("electric force and field", "charges create fields that exert force on other charges", "apply inverse-square proportionality and superposition", "electric field direction is defined for a positive test charge"),
        _c("voltage and capacitance", "voltage is potential energy per charge and capacitors store separated charge", "relate charge, voltage, and capacitance", "a dielectric increases capacitance but its effect on voltage depends on whether the capacitor remains connected"),
        _c("circuits", "current, resistance, and voltage obey conservation and Ohm's law in simple components", "reduce series and parallel networks", "parallel branches share voltage, while series elements share current"),
        _c("waves and sound", "wave speed equals frequency times wavelength", "predict frequency, wavelength, intensity, and Doppler changes", "frequency is set by the source and does not change merely because wave speed changes at a boundary"),
        _c("geometric optics", "reflection and refraction determine image formation by mirrors and lenses", "use ray diagrams and the thin-lens equation", "a real image can be projected; a virtual image cannot"),
    )),
    Course("foundation-19-core", "19 Psychology Foundations", (
        _c("classical conditioning", "a neutral stimulus gains predictive power through association", "identify acquisition, extinction, generalization, and discrimination", "extinction suppresses a learned response rather than erasing all learning"),
        _c("operant conditioning", "behavior changes according to its consequences", "classify positive and negative reinforcement and punishment", "negative reinforcement increases behavior and is not punishment"),
        _c("memory systems", "sensory, working, and long-term memory involve distinct processes", "distinguish encoding, storage, retrieval, and interference", "recognition is generally easier than free recall"),
        _c("development", "biological, cognitive, and social changes unfold across the lifespan", "compare major developmental theories and milestones", "stage theories describe patterns but should not be treated as exact clocks for every person"),
        _c("psychological disorders", "diagnosis considers patterns of cognition, emotion, behavior, distress, and impairment", "distinguish symptom clusters without overdiagnosing normal variation", "a single symptom rarely establishes a disorder"),
    )),
    Course("foundation-20-core", "20 Sociology Foundations", (
        _c("culture and socialization", "shared symbols, norms, values, and learning shape behavior", "distinguish norms, roles, sanctions, and agents of socialization", "culture influences behavior without making every member identical"),
        _c("social structure", "institutions, statuses, roles, groups, and networks organize social life", "analyze how position shapes opportunities and expectations", "role conflict occurs between roles, while role strain occurs within one role"),
        _c("stratification", "resources and power are distributed unequally across social categories", "compare class, status, mobility, and intersectionality", "individual achievement does not eliminate structural constraints"),
        _c("demography", "population size and composition change through fertility, mortality, and migration", "interpret population pyramids and demographic transition", "population growth depends on rates and age structure, not only current births"),
        _c("health disparities", "social conditions influence exposure, access, stress, and health outcomes", "separate individual risk factors from structural determinants", "an observed group difference does not establish a biological cause"),
    )),
    Course("foundation-21-core", "21 Integrated Foundation Review", (
        _c("multistep scientific reasoning", "complex problems require translating evidence across biological, chemical, physical, and behavioral levels", "state knowns, unknowns, assumptions, and a testable chain of reasoning", "jumping directly to a memorized equation can hide an incorrect model"),
        _c("proportional reasoning", "many MCAT questions can be solved by tracking how one quantity scales with another", "use direct, inverse, square, and logarithmic relationships", "adding percentages is unsafe when changes compound"),
        _c("experimental critique", "strong conclusions require valid controls, adequate measurement, and appropriate scope", "identify bias, confounding, random error, and external-validity limits", "statistical significance does not guarantee clinical or practical importance"),
        _c("cross-system integration", "organ systems exchange matter, energy, and information to maintain homeostasis", "connect respiratory, cardiovascular, renal, endocrine, and nervous responses", "a local change can trigger compensations that obscure the original disturbance"),
        _c("passage strategy", "passages provide a model, evidence, and constraints that must guide content knowledge", "map claims, variables, figures, and causal links before answering", "outside knowledge should clarify the passage, not override stated experimental facts"),
    )),
)

# Compatibility with existing callers/tests that use tuple unpacking.
COURSES = tuple((course.key, course.name, course.concepts) for course in COURSES)


def _cards_for(course_name: str, concept: Concept) -> tuple[tuple[str, str, str], ...]:
    name, explanation, application, trap = concept
    return (
        (f"What is {name}?", explanation.capitalize() + ".", f"Course: {course_name}. Build a one-sentence definition before checking the answer."),
        (f"What mechanism or relationship is central to {name}?", explanation.capitalize() + ".", f"Connect the mechanism to this use: {application}."),
        (f"How would you apply {name} in an MCAT-style problem?", application.capitalize() + ".", f"First identify the relevant variables, units, structures, or evidence. Core idea: {explanation}."),
        (f"What should {name} be distinguished from?", trap.capitalize() + ".", f"Comparison questions often test the boundary of a concept rather than its definition."),
        (f"What prediction follows from {name}?", f"A valid prediction follows the relationship that {explanation}.", f"Use this practical setting: {application}. State what changes, what stays controlled, and why."),
        (f"What common mistake should be avoided when reasoning about {name}?", trap.capitalize() + ".", f"Corrective rule: {explanation.capitalize()}."),
    )


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF)


def _diagram_png(course_index: int, variant: int) -> bytes:
    width, height = 640, 360
    background = (246, 248, 251)
    pixels = [list(background) for _ in range(width * height)]

    def fill(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for y in range(max(0, y0), min(height, y1)):
            offset = y * width
            for x in range(max(0, x0), min(width, x1)):
                pixels[offset + x] = list(color)

    palette = ((36, 99, 235), (14, 159, 110), (245, 158, 11), (220, 38, 38), (124, 58, 237))
    if variant == 0:
        for index, color in enumerate(palette):
            x0 = 35 + index * 120
            fill(x0, 105, x0 + 90, 245, color)
            if index < 4:
                fill(x0 + 90, 169, x0 + 120, 181, (60, 60, 70))
    else:
        fill(285, 140, 355, 220, palette[course_index % len(palette)])
        positions = ((70, 40), (500, 40), (70, 270), (500, 270), (285, 25))
        for index, ((x0, y0), color) in enumerate(zip(positions, palette, strict=True)):
            fill(x0, y0, x0 + 70, y0 + 55, color)
            cx, cy = x0 + 35, y0 + 27
            fill(min(cx, 320), min(cy, 180), max(cx, 320) + 4, max(cy, 180) + 4, (90, 90, 100))
    # Add a course/variant barcode so every generated diagram is unique.
    value = course_index * 2 + variant + 1
    for bit in range(8):
        if value & (1 << bit):
            fill(24 + bit * 16, 320, 34 + bit * 16, 344, (20, 20, 30))

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b"")


def install_phase1_content(store: StudyStore, curriculum_store: CurriculumStore) -> dict[str, int]:
    decks_created = cards_created = cards_skipped = 0
    media_attached = media_skipped = bindings = 0

    for course_index, (deck_key, deck_name, concepts) in enumerate(COURSES):
        deck = store.find_deck(deck_name)
        if deck is None:
            deck = store.create_deck(deck_name, f"Phase 1 lesson with 30 guided cards for {deck_name}.")
            decks_created += 1
        deck_id = int(deck["id"])
        existing_cards = store.list_cards(deck_id)
        existing = {str(card["question"]).strip().casefold(): card for card in existing_cards}

        for concept in concepts:
            for question, answer, notes in _cards_for(deck_name, concept):
                key = question.strip().casefold()
                if key in existing:
                    cards_skipped += 1
                    continue
                card = store.create_card(deck_id, question=question, answer=answer, notes=notes)
                existing[key] = card
                cards_created += 1

        refreshed = store.list_cards(deck_id)
        visual_cards = refreshed[:2]
        concept_legend = "; ".join(f"{index + 1}: {concept.name}" for index, concept in enumerate(concepts))
        for variant, card in enumerate(visual_cards):
            filename = f"{deck_key}-concept-map-{variant + 1}.png"
            data = base64.b64encode(_diagram_png(course_index, variant)).decode("ascii")
            try:
                store.add_card_media(
                    int(card["id"]), section="question", filename=filename, mime_type="image/png", data_base64=data
                )
            except StudyConflictError:
                media_skipped += 1
            else:
                media_attached += 1
            if concept_legend not in str(card["notes"]):
                store.update_card(int(card["id"]), notes=f"{card['notes']} Visual legend — {concept_legend}")

        curriculum_store.bind_deck(deck_key, deck_id)
        bindings += 1

    total_cards = sum(int(deck["card_count"]) for deck in store.list_decks() if deck["name"] in {name for _, name, _ in COURSES})
    return {
        "courses": len(COURSES),
        "decks_created": decks_created,
        "cards_created": cards_created,
        "cards_skipped": cards_skipped,
        "media_attached": media_attached,
        "media_skipped": media_skipped,
        "bindings": bindings,
        "total_cards": total_cards,
    }
