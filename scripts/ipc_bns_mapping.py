"""
Static crossreference: IPC 1860 -> BNS 2023, CrPC 1973 -> BNSS 2023,
Indian Evidence Act 1872 -> BSA 2023.

Scope and honesty constraints
-----------------------------
* This table is compiled from domain knowledge, NOT from an official
  government concordance. There is no authoritative machine-readable
  concordance in data/raw, and this pipeline runs offline, so nothing here has
  been checked against a primary source. Every entry therefore carries a
  `confidence` value and the whole table carries
  `verification_status = "unverified_against_official_concordance"`.
  Treat "high" as "widely reported and stable", not as "citable authority".

* What *is* machine-verified: every target section is checked to exist in the
  BNS/BNSS/BSA section inventories extracted in step 1, so a typo or an
  invented section number is caught. Source sections are likewise checked
  against the extracted IPC/CrPC inventories.

* The Indian Evidence Act 1872 is NOT in data/raw. IEA->BSA source sections
  therefore cannot be validated, only the BSA targets. This is flagged.

* Coverage is deliberately partial. Sections that would be guesswork are left
  out rather than filled in; `unmapped_cited_sections` in the report lists
  exactly which cited IPC sections still need manual work.

Relation vocabulary
-------------------
  one_to_one   provision carried over, renumbered
  merged       several old sections collapse into one new one
  split        one old section is distributed across several new ones
  narrowed     carried over with materially changed scope/elements
  omitted      no counterpart in the new code
  new          new provision with no predecessor
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTE_DIR = os.path.join(REPO, "data", "processed", "statutes")
CASELAW = os.path.join(REPO, "data", "processed", "caselaw", "indianbail_1200.json")
OUT_DIR = os.path.join(REPO, "data", "processed", "crossreference")

VERIFICATION_STATUS = "unverified_against_official_concordance"

# (source, target, relation, confidence, note)
IPC_TO_BNS: list[tuple[str, str | None, str, str, str]] = [
    ("34", "3(5)", "one_to_one", "high", "Common intention."),
    ("107", "45", "one_to_one", "high", "Abetment defined."),
    ("109", "49", "one_to_one", "high", "Abetment, offence committed."),
    ("110", "50", "one_to_one", "high", ""),
    ("111", "51", "one_to_one", "high", ""),
    ("114", "46", "one_to_one", "high", "Abettor present."),
    ("116", "55", "one_to_one", "high", ""),
    ("120A", "61(1)", "one_to_one", "high", "Criminal conspiracy defined."),
    ("120B", "61(2)", "one_to_one", "high", "Punishment for criminal conspiracy."),
    ("121", "147", "one_to_one", "high", "Waging war against Government of India."),
    ("121A", "148", "one_to_one", "high", ""),
    ("122", "149", "one_to_one", "high", ""),
    ("124A", None, "omitted", "high",
     "Sedition repealed. BNS 152 (act endangering sovereignty, unity and "
     "integrity) is NOT a renumbering -- different elements and scope."),
    ("141", "189(1)", "one_to_one", "high", "Unlawful assembly."),
    ("143", "189(2)", "one_to_one", "high", ""),
    ("147", "191(2)", "one_to_one", "high", "Rioting."),
    ("148", "191(3)", "one_to_one", "high", "Rioting, armed with deadly weapon."),
    ("149", "190", "one_to_one", "high", "Vicarious liability of assembly members."),
    ("153A", "196", "one_to_one", "high", "Promoting enmity between groups."),
    ("153B", "197", "one_to_one", "high", ""),
    ("166", "198", "one_to_one", "high", ""),
    ("166A", "199", "one_to_one", "high", ""),
    ("170", "205", "one_to_one", "high", "Personating a public servant."),
    ("174A", "209", "one_to_one", "high", "Non-appearance after proclamation."),
    ("182", "217", "one_to_one", "high", "False information to public servant."),
    ("186", "221", "one_to_one", "high", "Obstructing public servant."),
    ("188", "223", "one_to_one", "high", "Disobedience to order of public servant."),
    ("189", "222", "one_to_one", "high", ""),
    ("191", "227", "one_to_one", "high", "Giving false evidence."),
    ("193", "229", "one_to_one", "high", "Punishment for false evidence."),
    ("201", "238", "one_to_one", "high", "Causing disappearance of evidence."),
    ("211", "248", "one_to_one", "high", "False charge of offence."),
    ("212", "249", "one_to_one", "high", "Harbouring an offender."),
    ("213", "250", "one_to_one", "high", ""),
    ("218", "234", "one_to_one", "high", ""),
    ("224", "262", "one_to_one", "high", ""),
    ("225", "263", "one_to_one", "high", ""),
    ("269", "271", "one_to_one", "high", "Negligent act likely to spread infection."),
    ("270", "272", "one_to_one", "high", ""),
    ("279", "281", "one_to_one", "high", "Rash driving on a public way."),
    ("294", "296", "one_to_one", "high", "Obscene acts and songs."),
    ("295", "298", "one_to_one", "high", "Injuring a place of worship."),
    ("299", "100", "one_to_one", "high", "Culpable homicide defined."),
    ("300", "101", "one_to_one", "high", "Murder defined."),
    ("302", "103(1)", "one_to_one", "high", "Punishment for murder."),
    ("303", "104", "one_to_one", "high", "Murder by life convict."),
    ("304", "105", "one_to_one", "high", "Culpable homicide not amounting to murder."),
    ("304A", "106(1)", "narrowed", "high",
     "Death by negligence. BNS 106(2) adds a distinct, heavier offence for "
     "fleeing without reporting -- no IPC predecessor."),
    ("304B", "80", "one_to_one", "high",
     "Dowry death: BNS 80(1) defines, 80(2) punishes."),
    ("305", "107", "one_to_one", "high", "Abetment of suicide of child/insane person."),
    ("306", "108", "one_to_one", "high", "Abetment of suicide."),
    ("307", "109", "one_to_one", "high", "Attempt to murder."),
    ("308", "110", "one_to_one", "high", "Attempt to commit culpable homicide."),
    ("309", None, "omitted", "medium",
     "Attempt to suicide not re-enacted as a general offence; BNS 226 covers "
     "only attempt to suicide to compel/restrain a public servant."),
    ("313", "89", "one_to_one", "high", "Causing miscarriage without consent."),
    ("315", "91", "one_to_one", "high", ""),
    ("316", "90", "one_to_one", "medium", "Causing death of a quick unborn child."),
    ("319", "114", "one_to_one", "high", "Hurt defined."),
    ("320", "116", "one_to_one", "high", "Grievous hurt defined."),
    ("323", "115(2)", "one_to_one", "high", "Punishment for voluntarily causing hurt."),
    ("324", "118(1)", "one_to_one", "high", "Hurt by dangerous weapons."),
    ("325", "117(2)", "one_to_one", "high", "Punishment for grievous hurt."),
    ("326", "118(2)", "one_to_one", "high", "Grievous hurt by dangerous weapons."),
    ("326A", "124(1)", "one_to_one", "high", "Acid attack."),
    ("326B", "124(2)", "one_to_one", "high", "Attempted acid attack."),
    ("328", "123", "one_to_one", "high", "Hurt by poison."),
    ("330", "120(1)", "one_to_one", "high", "Hurt to extort confession."),
    ("332", "121(1)", "one_to_one", "high", "Hurt to deter public servant."),
    ("333", "121(2)", "one_to_one", "high", "Grievous hurt to deter public servant."),
    ("336", "125", "one_to_one", "high", "Act endangering life or personal safety."),
    ("337", "125(a)", "one_to_one", "high", ""),
    ("338", "125(b)", "one_to_one", "high", ""),
    ("339", "126(1)", "one_to_one", "high", "Wrongful restraint."),
    ("340", "127(1)", "one_to_one", "high", "Wrongful confinement."),
    ("341", "126(2)", "one_to_one", "high", "Punishment for wrongful restraint."),
    ("342", "127(2)", "one_to_one", "high", "Punishment for wrongful confinement."),
    ("343", "127(3)", "one_to_one", "high", ""),
    ("349", "128", "one_to_one", "high", "Force defined."),
    ("350", "129", "one_to_one", "high", "Criminal force defined."),
    ("351", "130", "one_to_one", "high", "Assault defined."),
    ("352", "131", "one_to_one", "high", ""),
    ("354", "74", "one_to_one", "high", "Outraging modesty of a woman."),
    ("354A", "75", "one_to_one", "high", "Sexual harassment."),
    ("354B", "76", "one_to_one", "high", "Assault to disrobe."),
    ("354C", "77", "one_to_one", "high", "Voyeurism."),
    ("354D", "78", "one_to_one", "high", "Stalking."),
    ("359", "135", "one_to_one", "high", "Kidnapping."),
    ("360", "136", "one_to_one", "high", ""),
    ("361", "137(1)", "one_to_one", "high", "Kidnapping from lawful guardianship."),
    ("363", "137(2)", "one_to_one", "high", "Punishment for kidnapping."),
    ("364", "140(1)", "one_to_one", "high", "Kidnapping to murder."),
    ("364A", "140(2)", "one_to_one", "high", "Kidnapping for ransom."),
    ("365", "140(3)", "one_to_one", "high", ""),
    ("366", "87", "one_to_one", "high", "Kidnapping/abducting a woman to compel marriage."),
    ("366A", "96", "one_to_one", "high", "Procuration of a minor girl."),
    ("366B", "97", "one_to_one", "medium", "Importation of a girl from a foreign country."),
    ("368", "139", "one_to_one", "high", "Concealing a kidnapped person."),
    ("370", "143", "one_to_one", "high", "Trafficking in persons."),
    ("370A", "144", "one_to_one", "high", "Exploitation of a trafficked person."),
    ("372", "98", "one_to_one", "high", "Selling a minor for prostitution."),
    ("373", "99", "one_to_one", "high", "Buying a minor for prostitution."),
    ("375", "63", "one_to_one", "high", "Rape defined."),
    ("376", "64", "one_to_one", "high", "Punishment for rape."),
    ("376AB", "65(2)", "one_to_one", "high", "Rape of a woman under 12."),
    ("376B", "67", "one_to_one", "high", "Sexual intercourse by husband on separation."),
    ("376C", "68", "one_to_one", "high", "Sexual intercourse by a person in authority."),
    ("376D", "70(1)", "one_to_one", "high", "Gang rape."),
    ("376DA", "70(2)", "merged", "high",
     "IPC 376DA (gang rape of a woman under 16) and 376DB (under 12) are "
     "merged into BNS 70(2)."),
    ("376DB", "70(2)", "merged", "high", "See 376DA."),
    ("376E", "71", "one_to_one", "high", "Repeat offenders."),
    ("377", None, "omitted", "high",
     "No counterpart in the BNS. Non-consensual acts against men and "
     "transgender persons are consequently not covered by a general provision."),
    ("378", "303(1)", "one_to_one", "high", "Theft defined."),
    ("379", "303(2)", "one_to_one", "high", "Punishment for theft."),
    ("380", "305", "one_to_one", "high", "Theft in a dwelling house."),
    ("381", "306", "one_to_one", "high", "Theft by clerk or servant."),
    ("383", "308(1)", "one_to_one", "high", "Extortion defined."),
    ("384", "308(2)", "one_to_one", "high", "Punishment for extortion."),
    ("385", "308(3)", "one_to_one", "high", ""),
    ("386", "308(4)", "one_to_one", "high", ""),
    ("387", "308(5)", "one_to_one", "high", ""),
    ("388", "308(6)", "one_to_one", "high", ""),
    ("389", "308(7)", "one_to_one", "high", ""),
    ("390", "309(1)", "one_to_one", "high", "Robbery defined."),
    ("392", "309(4)", "one_to_one", "high", "Punishment for robbery."),
    ("393", "309(5)", "one_to_one", "high", "Attempt to commit robbery."),
    ("394", "309(6)", "one_to_one", "high", "Hurt caused in robbery."),
    ("395", "310(2)", "one_to_one", "high", "Punishment for dacoity."),
    ("396", "310(3)", "one_to_one", "high", "Dacoity with murder."),
    ("397", "311", "merged", "high",
     "IPC 397 and 398 both map onto BNS 311."),
    ("398", "311", "merged", "high", "See 397."),
    ("399", "310(4)", "one_to_one", "high", "Preparation to commit dacoity."),
    ("402", "310(5)", "one_to_one", "high", "Assembling for dacoity."),
    ("403", "314", "one_to_one", "high", "Dishonest misappropriation."),
    ("405", "316(1)", "one_to_one", "high", "Criminal breach of trust defined."),
    ("406", "316(2)", "one_to_one", "high", "Punishment for criminal breach of trust."),
    ("407", "316(3)", "one_to_one", "high", ""),
    ("408", "316(4)", "one_to_one", "high", ""),
    ("409", "316(5)", "one_to_one", "high", "Breach of trust by public servant/banker."),
    ("411", "317(2)", "one_to_one", "high", "Receiving stolen property."),
    ("412", "317(4)", "one_to_one", "high", ""),
    ("413", "317(5)", "one_to_one", "medium", "Habitual dealing in stolen property."),
    ("415", "318(1)", "one_to_one", "high", "Cheating defined."),
    ("417", "318(2)", "one_to_one", "high", "Punishment for cheating."),
    ("418", "318(3)", "one_to_one", "high", ""),
    ("419", "319(2)", "one_to_one", "high", "Cheating by personation."),
    ("420", "318(4)", "one_to_one", "high",
     "Cheating and dishonestly inducing delivery of property."),
    ("425", "324(1)", "one_to_one", "high", "Mischief defined."),
    ("426", "324(2)", "one_to_one", "high", ""),
    ("427", "324(4)", "one_to_one", "high", "Mischief causing damage."),
    ("441", "329(1)", "one_to_one", "high", "Criminal trespass."),
    ("442", "329(2)", "one_to_one", "high", "House-trespass."),
    ("447", "329(3)", "one_to_one", "high", "Punishment for criminal trespass."),
    ("448", "329(4)", "one_to_one", "high", "Punishment for house-trespass."),
    ("451", "331(2)", "one_to_one", "medium", ""),
    ("452", "331(4)", "one_to_one", "high", "House-trespass after preparation for hurt."),
    ("453", "331(1)", "one_to_one", "medium", ""),
    ("454", "331(3)", "one_to_one", "medium", ""),
    ("457", "331(6)", "one_to_one", "medium", ""),
    ("458", "331(7)", "one_to_one", "medium", ""),
    ("459", "331(8)", "one_to_one", "medium", ""),
    ("460", "331(9)", "one_to_one", "medium", ""),
    ("463", "335", "one_to_one", "high", "Forgery defined."),
    ("465", "336(2)", "one_to_one", "high", "Punishment for forgery."),
    ("466", "337", "one_to_one", "high", "Forgery of a court record."),
    ("467", "338", "one_to_one", "high", "Forgery of a valuable security."),
    ("468", "336(3)", "one_to_one", "high", "Forgery for the purpose of cheating."),
    ("469", "336(4)", "one_to_one", "high", "Forgery to harm reputation."),
    ("471", "340(2)", "one_to_one", "high", "Using a forged document as genuine."),
    ("477A", "344", "one_to_one", "high", "Falsification of accounts."),
    ("489A", "178", "one_to_one", "high", "Counterfeiting currency notes."),
    ("489B", "179", "one_to_one", "high", ""),
    ("489C", "180", "one_to_one", "high", "Possession of forged currency notes."),
    ("493", "81", "one_to_one", "high", "Cohabitation caused by deceit."),
    ("494", "82(1)", "one_to_one", "high", "Bigamy."),
    ("495", "82(2)", "one_to_one", "high", ""),
    ("496", "83", "one_to_one", "high", "Fraudulent marriage ceremony."),
    ("497", None, "omitted", "high",
     "Adultery; already struck down in Joseph Shine v. Union of India (2018) "
     "and not re-enacted."),
    ("498", "84", "one_to_one", "high", "Enticing a married woman."),
    ("498A", "85", "split", "high",
     "Cruelty by husband or relatives. BNS 85 carries the offence; the "
     "definition in the IPC Explanation becomes a standalone BNS 86."),
    ("499", "356(1)", "one_to_one", "high", "Defamation defined."),
    ("500", "356(2)", "one_to_one", "high", "Punishment for defamation."),
    ("503", "351(1)", "one_to_one", "high", "Criminal intimidation defined."),
    ("504", "352", "one_to_one", "high", "Intentional insult to provoke breach of peace."),
    ("505", "353", "one_to_one", "high", "Statements conducing to public mischief."),
    ("506", "351(2)", "split", "high",
     "IPC 506 Part I -> BNS 351(2); Part II (threat to cause death/grievous "
     "hurt) -> BNS 351(3). Case data citing '506(II)' maps to 351(3)."),
    ("507", "351(4)", "one_to_one", "high", "Criminal intimidation by anonymous means."),
    ("509", "79", "one_to_one", "high", "Word or gesture insulting a woman's modesty."),
    ("511", "62", "one_to_one", "high", "Punishment for attempting to commit offences."),
]

# Provisions in the new codes with no IPC predecessor.
BNS_NEW_PROVISIONS: list[tuple[str, str]] = [
    ("69", "Sexual intercourse by employing deceitful means or a false promise "
           "of marriage."),
    ("103(2)", "Murder by a group of five or more on grounds of race, caste, "
               "community, sex, birthplace, language or personal belief "
               "(mob lynching)."),
    ("106(2)", "Causing death by rash/negligent driving and fleeing without "
               "reporting to police or magistrate."),
    ("111", "Organised crime."),
    ("112", "Petty organised crime."),
    ("113", "Terrorist act (previously reachable only under the UAPA)."),
    ("152", "Act endangering sovereignty, unity and integrity of India "
            "(occupies the space vacated by sedition, with different elements)."),
    ("304", "Snatching."),
]

CRPC_TO_BNSS: list[tuple[str, str | None, str, str, str]] = [
    ("41", "35", "one_to_one", "high", "When police may arrest without warrant."),
    ("41A", "35(3)", "one_to_one", "high", "Notice of appearance."),
    ("41D", "38", "one_to_one", "high", "Right to meet an advocate during interrogation."),
    ("46", "43", "narrowed", "high",
     "Arrest, how made. BNSS 43(3) newly permits use of handcuffs in "
     "specified cases."),
    ("50", "47", "one_to_one", "high", "Right to be informed of grounds of arrest."),
    ("57", "58", "one_to_one", "high", "Person arrested not to be detained over 24 hours."),
    ("91", "94", "one_to_one", "high", "Summons to produce a document."),
    ("125", "144", "one_to_one", "high", "Maintenance of wives, children, parents."),
    ("144", "163", "one_to_one", "high", "Urgent orders in nuisance/apprehended danger."),
    ("154", "173", "narrowed", "high",
     "FIR. BNSS 173 newly permits registration irrespective of territorial "
     "jurisdiction (Zero FIR) and electronic filing."),
    ("156", "175", "one_to_one", "high", "Police power to investigate."),
    ("157", "176", "one_to_one", "high", "Procedure for investigation."),
    ("161", "180", "one_to_one", "high", "Examination of witnesses by police."),
    ("164", "183", "one_to_one", "high", "Recording of confessions and statements."),
    ("167", "187", "narrowed", "high",
     "Detention beyond 24 hours. The 15-day police custody period may now be "
     "sought in parts across the first 40/60 days."),
    ("173", "193", "one_to_one", "high", "Police report on completion of investigation."),
    ("176", "196", "one_to_one", "high", "Magisterial inquiry into a death in custody."),
    ("190", "210", "one_to_one", "high", "Cognizance of offences by Magistrates."),
    ("197", "218", "one_to_one", "high", "Prosecution of judges and public servants."),
    ("200", "223", "one_to_one", "high", "Examination of the complainant."),
    ("202", "225", "one_to_one", "high", "Postponement of issue of process."),
    ("204", "227", "one_to_one", "high", "Issue of process."),
    ("207", "230", "one_to_one", "high", "Supply of copies to the accused."),
    ("227", "250", "one_to_one", "high", "Discharge."),
    ("228", "251", "one_to_one", "high", "Framing of charge."),
    ("239", "262", "one_to_one", "high", "Discharge in warrant cases."),
    ("313", "351", "one_to_one", "high", "Power to examine the accused."),
    ("320", "359", "one_to_one", "high", "Compounding of offences."),
    ("321", "360", "one_to_one", "high", "Withdrawal from prosecution."),
    ("357", "395", "one_to_one", "high", "Order to pay compensation."),
    ("360", "401", "one_to_one", "high", "Release on probation of good conduct."),
    ("372", "413", "one_to_one", "high", "Victim's right of appeal."),
    ("374", "415", "one_to_one", "high", "Appeals from convictions."),
    ("378", "419", "one_to_one", "high", "Appeal in case of acquittal."),
    ("389", "430", "one_to_one", "high", "Suspension of sentence pending appeal."),
    ("397", "438", "one_to_one", "high", "Revision."),
    ("401", "442", "one_to_one", "high", "High Court's powers of revision."),
    ("436", "478", "one_to_one", "high", "Bail in bailable offences."),
    ("436A", "479", "narrowed", "high",
     "Maximum period of detention. BNSS 479 adds release on bond after "
     "one-third of the maximum sentence for a first-time offender, and bars "
     "the benefit for offences punishable with life."),
    ("437", "480", "one_to_one", "high", "Bail in non-bailable offences."),
    ("438", "482", "one_to_one", "high", "Anticipatory bail."),
    ("439", "483", "one_to_one", "high", "Special powers of High Court/Sessions Court."),
    ("468", "514", "one_to_one", "high", "Bar to taking cognizance after limitation."),
    ("482", "528", "one_to_one", "high", "Saving of inherent powers of the High Court."),
]

BNSS_NEW_PROVISIONS: list[tuple[str, str]] = [
    ("105", "Audio-video recording of search and seizure."),
    ("356", "Trial in absentia of a proclaimed offender."),
    ("398", "Witness protection scheme."),
    ("530", "Trial, inquiry and proceedings in electronic mode."),
]

# The Indian Evidence Act 1872 is not present in data/raw, so these source
# sections cannot be validated against extracted text.
IEA_TO_BSA: list[tuple[str, str | None, str, str, str]] = [
    ("3", "2", "one_to_one", "high", "Interpretation clause."),
    ("5", "3", "one_to_one", "high", "Evidence may be given of facts in issue."),
    ("8", "6", "one_to_one", "high", "Motive, preparation and conduct."),
    ("17", "15", "one_to_one", "high", "Admission defined."),
    ("24", "22", "one_to_one", "high", "Confession caused by inducement."),
    ("25", "23(1)", "one_to_one", "high", "Confession to a police officer."),
    ("26", "23(2)", "one_to_one", "high", "Confession in police custody."),
    ("27", "23(2)", "merged", "medium",
     "The proviso on discovery of facts sits inside BSA 23(2)."),
    ("32", "26", "one_to_one", "high", "Dying declaration and related statements."),
    ("45", "39", "one_to_one", "high", "Opinion of experts."),
    ("45A", "39(2)", "one_to_one", "high", "Opinion of the Examiner of Electronic Evidence."),
    ("60", "55", "one_to_one", "high", "Oral evidence must be direct."),
    ("61", "56", "one_to_one", "high", "Proof of contents of documents."),
    ("62", "57", "one_to_one", "high", "Primary evidence."),
    ("63", "58", "one_to_one", "high", "Secondary evidence."),
    ("65A", "63", "merged", "high",
     "IEA 65A/65B are consolidated into BSA 63, which materially expands the "
     "certificate requirement for electronic records."),
    ("65B", "63", "merged", "high", "See 65A."),
    ("101", "104", "one_to_one", "high", "Burden of proof."),
    ("106", "109", "one_to_one", "high", "Facts especially within knowledge."),
    ("113A", "116", "one_to_one", "high", "Presumption as to abetment of suicide."),
    ("113B", "117", "one_to_one", "high", "Presumption as to dowry death."),
    ("114", "119", "one_to_one", "high", "Court may presume existence of facts."),
    ("114A", "120", "one_to_one", "high", "Presumption as to absence of consent in rape."),
    ("118", "124", "one_to_one", "high", "Who may testify."),
    ("133", "138", "one_to_one", "high", "Accomplice."),
    ("145", "148", "one_to_one", "high", "Cross-examination as to previous statements."),
]


# --------------------------------------------------------------------------

def load_inventory(fname: str) -> set[str]:
    path = os.path.join(STATUTE_DIR, fname)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {str(r["section_number"]).upper() for r in json.load(fh)}


def base_section(ref: str | None) -> str | None:
    """'103(1)' -> '103';  '125(a)' -> '125'."""
    if not ref:
        return None
    m = re.match(r"^(\d{1,3}[A-Z]{0,2})", ref.upper())
    return m.group(1) if m else None


def cited_ipc_counts() -> Counter:
    if not os.path.exists(CASELAW):
        return Counter()
    with open(CASELAW, encoding="utf-8") as fh:
        cases = json.load(fh)
    c: Counter = Counter()
    for case in cases:
        for cit in case["cited_sections"]:
            if cit["statute"].startswith("Indian Penal") and cit["section"]:
                c[cit["section"].upper()] += 1
    return c


def build() -> dict:
    inv = {
        "IPC": load_inventory("criminal_law__ipc_1860_archived.json"),
        "CrPC": load_inventory("criminal_law__crpc_1973_archived.json"),
        "BNS": load_inventory("criminal_law__bns_2023.json"),
        "BNSS": load_inventory("criminal_law__bnss_2023.json"),
        "BSA": load_inventory("criminal_law__bna_2023.json"),
    }
    usage = cited_ipc_counts()

    problems: list[str] = []
    entries: list[dict] = []

    def add(table, src_code, dst_code, validate_source=True):
        for src, dst, relation, conf, note in table:
            src_ok = (not validate_source) or (src.upper() in inv[src_code])
            dst_base = base_section(dst)
            dst_ok = dst is None or (dst_base in inv[dst_code])
            if validate_source and not src_ok:
                problems.append(f"{src_code} s.{src} not found in extracted {src_code}")
            if dst is not None and not dst_ok:
                problems.append(f"{dst_code} s.{dst} not found in extracted {dst_code}")
            entries.append({
                "source_statute": src_code,
                "source_section": src,
                "target_statute": dst_code if dst else None,
                "target_section": dst,
                "relation": relation,
                "confidence": conf,
                "note": note,
                "source_section_verified_in_corpus": src_ok if validate_source else None,
                "target_section_verified_in_corpus": dst_ok if dst else None,
                # The bail dataset only carries IPC section citations, so this
                # count is meaningful for IPC rows alone. Looking it up for
                # CrPC/IEA rows would silently report IPC s.167's count against
                # CrPC s.167.
                "caselaw_citations": (
                    usage.get(src.upper(), 0) if src_code == "IPC" else None
                ),
            })

    add(IPC_TO_BNS, "IPC", "BNS")
    add(CRPC_TO_BNSS, "CrPC", "BNSS")
    add(IEA_TO_BSA, "IEA", "BSA", validate_source=False)

    for sec, desc in BNS_NEW_PROVISIONS:
        entries.append({
            "source_statute": None, "source_section": None,
            "target_statute": "BNS", "target_section": sec,
            "relation": "new", "confidence": "high", "note": desc,
            "source_section_verified_in_corpus": None,
            "target_section_verified_in_corpus": base_section(sec) in inv["BNS"],
            "caselaw_citations": 0,
        })
    for sec, desc in BNSS_NEW_PROVISIONS:
        entries.append({
            "source_statute": None, "source_section": None,
            "target_statute": "BNSS", "target_section": sec,
            "relation": "new", "confidence": "high", "note": desc,
            "source_section_verified_in_corpus": None,
            "target_section_verified_in_corpus": base_section(sec) in inv["BNSS"],
            "caselaw_citations": 0,
        })

    mapped_ipc = {e["source_section"].upper() for e in entries
                  if e["source_statute"] == "IPC"}
    unmapped = [(s, n) for s, n in usage.most_common() if s not in mapped_ipc]
    covered = sum(n for s, n in usage.items() if s in mapped_ipc)

    return {
        "verification_status": VERIFICATION_STATUS,
        "caveat": "Compiled from domain knowledge and not checked against an "
                  "official government concordance. Section numbers are "
                  "machine-verified to exist in the extracted statute text; "
                  "the correctness of each pairing is not.",
        "entries": entries,
        "validation_problems": problems,
        "coverage": {
            "distinct_ipc_sections_in_caselaw": len(usage),
            "distinct_ipc_sections_mapped": len(
                [s for s in usage if s in mapped_ipc]),
            "caselaw_citations_total": sum(usage.values()),
            "caselaw_citations_covered": covered,
            "caselaw_citation_coverage_pct": round(
                100 * covered / sum(usage.values()), 1) if usage else 0.0,
            "unmapped_cited_sections": [
                {"section": s, "citations": n} for s, n in unmapped
            ],
        },
        "inventory_sizes": {k: len(v) for k, v in inv.items()},
    }


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    data = build()
    cov = data["coverage"]

    by_rel = Counter(e["relation"] for e in data["entries"])
    print(f"crossref entries            : {len(data['entries'])}")
    print(f"  by relation               : {dict(by_rel)}")
    print(f"inventory sizes             : {data['inventory_sizes']}")
    print()
    print(f"IPC sections cited in caselaw    : {cov['distinct_ipc_sections_in_caselaw']}")
    print(f"  of those, mapped               : {cov['distinct_ipc_sections_mapped']}")
    print(f"citation-weighted coverage       : {cov['caselaw_citation_coverage_pct']}% "
          f"({cov['caselaw_citations_covered']}/{cov['caselaw_citations_total']})")
    print()
    print("non-1:1 mappings")
    for e in data["entries"]:
        if e["relation"] in ("merged", "split", "narrowed", "omitted"):
            tgt = f"{e['target_statute']} {e['target_section']}" if e["target_section"] else "NONE"
            cites = (f"{e['caselaw_citations']} citations"
                     if e["caselaw_citations"] is not None else "n/a")
            print(f"  [{e['relation']:<8}] {e['source_statute']} {e['source_section']:<6}"
                  f" -> {tgt:<12} ({cites})")
    print()
    if data["validation_problems"]:
        print(f"VALIDATION PROBLEMS ({len(data['validation_problems'])}):")
        for p in data["validation_problems"][:30]:
            print(f"  ! {p}")
    else:
        print("validation: every source and target section exists in the "
              "extracted statute text.")
    print()
    top_unmapped = cov["unmapped_cited_sections"][:20]
    print(f"top unmapped cited IPC sections ({len(cov['unmapped_cited_sections'])} total):")
    print("  " + ", ".join(f"{u['section']}({u['citations']})" for u in top_unmapped))

    if not dry:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "ipc_bns_mapping.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print(f"\nwrote {OUT_DIR}")
    else:
        print("\nDRY RUN -- nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
