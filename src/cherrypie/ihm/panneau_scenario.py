"""Section « Scénario » : on compose une suite de lancements, puis on la lance d'un bloc."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cherrypie.commun.erreurs import ScenarioInvalideError
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.scenario import LigneScenario, Scenario
from cherrypie.ihm.style import NOMS_CATEGORIE
from cherrypie.modele.usager import CLASSES_PAR_CATEGORIE, Pieton

NOMBRE_MAX_PAR_LIGNE = 10
DELAI_MAX = 120.0
PAS_DU_DELAI = 0.5
MILLISECONDES_PAR_SECONDE = 1000
# Attente maximale de l'arrêt de chaque client, en secondes, quand on arrête tout.
DELAI_ARRET = 2.0
FILTRE_FICHIERS = "Scénarios (*.json)"

journal = logging.getLogger(__name__)


class PanneauScenario(QWidget):
    """Composition et lancement d'un scénario.

    On choisit le type d'usager, l'entrée, la sortie, le nombre et le délai depuis la
    ligne précédente, puis on ajoute la ligne. La liste se réordonne avec les boutons ou
    par glisser-déposer. « Lancer le scénario » programme chaque ligne à son instant ;
    « Arrêter tout » annule ce qui n'est pas encore parti et arrête les clients lancés.
    Le scénario s'enregistre et se recharge en JSON, pour rejouer une démonstration.
    """

    def __init__(self, lanceur: LanceurClients, parent: QWidget | None = None) -> None:
        """Construit la section.

        Args:
            lanceur (LanceurClients): lanceur qui crée les clients.
            parent (QWidget | None): widget parent.
        """
        super().__init__(parent)
        self.__lanceur = lanceur
        branches = lanceur.config.branches
        self.__branches = {branche.nom for branche in branches}
        self.__minuteries: list[QTimer] = []
        self.__choix_categorie = QComboBox()
        for categorie in CLASSES_PAR_CATEGORIE:
            self.__choix_categorie.addItem(NOMS_CATEGORIE[categorie], categorie)
        self.__choix_entree = QComboBox()
        self.__choix_sortie = QComboBox()
        for branche in branches:
            self.__choix_entree.addItem(branche.libelle, branche.nom)
            self.__choix_sortie.addItem(branche.libelle, branche.nom)
        self.__choix_nombre = QSpinBox()
        self.__choix_nombre.setRange(1, NOMBRE_MAX_PAR_LIGNE)
        self.__choix_delai = QDoubleSpinBox()
        self.__choix_delai.setRange(0.0, DELAI_MAX)
        self.__choix_delai.setSingleStep(PAS_DU_DELAI)
        self.__choix_delai.setSuffix(" s")
        self.__liste = QListWidget()
        self.__liste.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.__resume = QLabel()
        self.__boutons = {
            nom: QPushButton(texte)
            for nom, texte in (
                ("ajouter", "Ajouter au scénario"),
                ("monter", "Monter"),
                ("descendre", "Descendre"),
                ("supprimer", "Supprimer"),
                ("vider", "Vider"),
                ("enregistrer", "Enregistrer…"),
                ("charger", "Charger…"),
                ("lancer", "Lancer le scénario"),
                ("arreter", "Arrêter tout"),
            )
        }
        self.__disposer()
        self.__relier()
        self.__adapter_sortie()
        self.__mettre_a_jour_le_resume()

    @property
    def choix_categorie(self) -> QComboBox:
        """QComboBox: type d'usager ; la donnée de chaque entrée est la catégorie."""
        return self.__choix_categorie

    @property
    def choix_entree(self) -> QComboBox:
        """QComboBox: branche d'entrée ; la donnée de chaque ligne est l'identifiant de la branche."""
        return self.__choix_entree

    @property
    def choix_sortie(self) -> QComboBox:
        """QComboBox: branche de sortie, imposée égale à l'entrée pour un piéton."""
        return self.__choix_sortie

    @property
    def choix_nombre(self) -> QSpinBox:
        """QSpinBox: nombre d'usagers de la ligne."""
        return self.__choix_nombre

    @property
    def choix_delai(self) -> QDoubleSpinBox:
        """QDoubleSpinBox: délai depuis le lancement de la ligne précédente, en secondes."""
        return self.__choix_delai

    @property
    def liste(self) -> QListWidget:
        """QListWidget: lignes du scénario, dans l'ordre de lancement."""
        return self.__liste

    @property
    def boutons(self) -> dict[str, QPushButton]:
        """dict[str, QPushButton]: boutons de la section, par nom (copie)."""
        return dict(self.__boutons)

    @property
    def scenario(self) -> Scenario:
        """Scenario: scénario composé, dans l'ordre affiché."""
        rangs = range(self.__liste.count())
        return Scenario([self.__liste.item(rang).data(Qt.ItemDataRole.UserRole) for rang in rangs])

    @property
    def en_cours(self) -> bool:
        """bool: True tant que des lignes du scénario lancé attendent leur instant."""
        return any(minuterie.isActive() for minuterie in self.__minuteries)

    def ajouter(self) -> LigneScenario:
        """Ajoute en bas de la liste la ligne décrite par le formulaire.

        Returns:
            LigneScenario: la ligne ajoutée.
        """
        ligne = LigneScenario(
            self.__choix_categorie.currentData(),
            self.__choix_entree.currentData(),
            self.__choix_sortie.currentData(),
            self.__choix_nombre.value(),
            self.__choix_delai.value(),
        )
        self.__inserer(self.__liste.count(), ligne)
        self.__mettre_a_jour_le_resume()
        return ligne

    def deplacer(self, decalage: int) -> None:
        """Monte (décalage négatif) ou descend la ligne sélectionnée.

        Args:
            decalage (int): -1 pour monter d'un rang, 1 pour descendre.
        """
        rang = self.__liste.currentRow()
        cible = rang + decalage
        if rang < 0 or not 0 <= cible < self.__liste.count():
            return
        element = self.__liste.takeItem(rang)
        self.__liste.insertItem(cible, element)
        self.__liste.setCurrentRow(cible)

    def supprimer(self) -> None:
        """Retire la ligne sélectionnée."""
        rang = self.__liste.currentRow()
        if rang >= 0:
            self.__liste.takeItem(rang)
            self.__mettre_a_jour_le_resume()

    def vider(self) -> None:
        """Retire toutes les lignes."""
        self.__liste.clear()
        self.__mettre_a_jour_le_resume()

    def lancer(self) -> None:
        """Programme chaque ligne à son instant, depuis maintenant ; une ligne sans délai part tout de suite."""
        scenario = self.scenario
        for ligne, instant in zip(scenario.lignes, scenario.instants_de_depart()):
            minuterie = QTimer(self)
            minuterie.setSingleShot(True)
            minuterie.timeout.connect(lambda ligne=ligne: self.__lancer_ligne(ligne))
            minuterie.start(round(instant * MILLISECONDES_PAR_SECONDE))
            self.__minuteries.append(minuterie)
        journal.info("scénario lancé : %d ligne(s), %d usager(s)", len(scenario.lignes), scenario.nombre_d_usagers)

    def arreter_tout(self) -> None:
        """Annule les lignes pas encore parties et arrête tous les clients lancés."""
        for minuterie in self.__minuteries:
            minuterie.stop()
        self.__minuteries.clear()
        self.__lanceur.arreter_tous(DELAI_ARRET)

    def enregistrer(self, chemin: Path) -> None:
        """Enregistre le scénario en JSON.

        Args:
            chemin (Path): fichier à écrire.

        Raises:
            OSError: si le fichier ne peut pas être écrit.
        """
        chemin.write_text(self.scenario.vers_json(), encoding="utf-8")

    def charger(self, chemin: Path) -> None:
        """Remplace la liste par un scénario enregistré.

        Args:
            chemin (Path): fichier JSON à lire.

        Raises:
            OSError: si le fichier ne peut pas être lu.
            ScenarioInvalideError: si ce n'est pas un scénario valide pour ce rond-point.
        """
        scenario = Scenario.depuis_json(chemin.read_text(encoding="utf-8"), self.__branches)
        self.__liste.clear()
        for rang, ligne in enumerate(scenario.lignes):
            self.__inserer(rang, ligne)
        self.__mettre_a_jour_le_resume()

    def __lancer_ligne(self, ligne: LigneScenario) -> None:
        """Lance les usagers d'une ligne arrivée à son instant."""
        self.__lanceur.lancer(ligne.categorie, ligne.entree, ligne.sortie, ligne.nombre)
        self.__minuteries = [minuterie for minuterie in self.__minuteries if minuterie.isActive()]

    def __inserer(self, rang: int, ligne: LigneScenario) -> None:
        """Insère une ligne dans la liste, avec un texte lisible et la ligne en donnée."""
        trajet = self.__lanceur.trajet(ligne.categorie, ligne.entree, ligne.sortie)
        texte = f"+{ligne.delai:g} s   {ligne.nombre} × {NOMS_CATEGORIE[ligne.categorie]} : {trajet}"
        element = QListWidgetItem(texte)
        element.setData(Qt.ItemDataRole.UserRole, ligne)
        element.setToolTip(trajet)
        self.__liste.insertItem(rang, element)

    def __mettre_a_jour_le_resume(self) -> None:
        """Résume le scénario : nombre de lignes, d'usagers et durée des lancements."""
        scenario = self.scenario
        instants = scenario.instants_de_depart()
        duree = instants[-1] if instants else 0.0
        self.__resume.setText(
            f"{len(scenario.lignes)} ligne(s), {scenario.nombre_d_usagers} usager(s), derniers départs à {duree:g} s"
        )

    def __adapter_sortie(self) -> None:
        """Un piéton traverse la branche par laquelle il arrive : sa sortie suit l'entrée."""
        pieton = self.__choix_categorie.currentData() == Pieton.CATEGORIE
        if pieton:
            self.__choix_sortie.setCurrentIndex(self.__choix_entree.currentIndex())
        self.__choix_sortie.setEnabled(not pieton)

    def __demander_enregistrement(self) -> None:
        """Demande un fichier puis y enregistre le scénario."""
        nom, _ = QFileDialog.getSaveFileName(self, "Enregistrer le scénario", "scenario.json", FILTRE_FICHIERS)
        if not nom:
            return
        try:
            self.enregistrer(Path(nom))
        except OSError as erreur:
            QMessageBox.warning(self, "Enregistrement impossible", str(erreur))

    def __demander_chargement(self) -> None:
        """Demande un fichier puis en charge le scénario."""
        nom, _ = QFileDialog.getOpenFileName(self, "Charger un scénario", "", FILTRE_FICHIERS)
        if not nom:
            return
        try:
            self.charger(Path(nom))
        except (OSError, ScenarioInvalideError) as erreur:
            QMessageBox.warning(self, "Chargement impossible", str(erreur))

    def __relier(self) -> None:
        """Relie les choix et les boutons à leurs actions."""
        self.__choix_categorie.currentIndexChanged.connect(self.__adapter_sortie)
        self.__choix_entree.currentIndexChanged.connect(self.__adapter_sortie)
        boutons = self.__boutons
        boutons["ajouter"].clicked.connect(self.ajouter)
        boutons["monter"].clicked.connect(lambda: self.deplacer(-1))
        boutons["descendre"].clicked.connect(lambda: self.deplacer(1))
        boutons["supprimer"].clicked.connect(self.supprimer)
        boutons["vider"].clicked.connect(self.vider)
        boutons["enregistrer"].clicked.connect(self.__demander_enregistrement)
        boutons["charger"].clicked.connect(self.__demander_chargement)
        boutons["lancer"].clicked.connect(self.lancer)
        boutons["arreter"].clicked.connect(self.arreter_tout)
        # Après un glisser-déposer, l'ordre a changé mais pas le contenu : le résumé reste juste.
        self.__liste.model().rowsMoved.connect(self.__mettre_a_jour_le_resume)

    def __disposer(self) -> None:
        """Place le formulaire, la liste et ses boutons, puis les boutons de lancement."""
        formulaire = QFormLayout()
        formulaire.addRow("Type", self.__choix_categorie)
        formulaire.addRow("Entrée", self.__choix_entree)
        formulaire.addRow("Sortie", self.__choix_sortie)
        formulaire.addRow("Nombre", self.__choix_nombre)
        formulaire.addRow("Délai", self.__choix_delai)
        composition = QGroupBox("Nouvelle ligne")
        disposition_composition = QVBoxLayout(composition)
        disposition_composition.addLayout(formulaire)
        disposition_composition.addWidget(self.__boutons["ajouter"])
        edition = QGridLayout()
        for rang, nom in enumerate(("monter", "descendre", "supprimer", "vider", "enregistrer", "charger")):
            edition.addWidget(self.__boutons[nom], rang // 2, rang % 2)
        lignes = QGroupBox("Scénario")
        disposition_lignes = QVBoxLayout(lignes)
        disposition_lignes.addWidget(self.__liste, 1)
        disposition_lignes.addWidget(self.__resume)
        disposition_lignes.addLayout(edition)
        lancement = QGridLayout()
        lancement.addWidget(self.__boutons["lancer"], 0, 0)
        lancement.addWidget(self.__boutons["arreter"], 0, 1)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(composition)
        disposition.addWidget(lignes, 1)
        disposition.addLayout(lancement)
