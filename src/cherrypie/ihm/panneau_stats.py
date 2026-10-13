"""Onglet « Statistiques » : temps de traversée du VP avec et sans régulation, densité dans le temps."""

from __future__ import annotations

from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cherrypie.ihm.style import COULEUR_FOND_GRAPHIQUE, COULEUR_TEXTE, COULEURS_SERIES

POURCENT = 100
TAILLE_POINT = 10
EPAISSEUR_LIGNE = 2
OPACITE_GRILLE = 0.2
# Marge au-dessus de la plus longue traversée, et de part et d'autre des numéros de traversée.
MARGE_HAUT = 1.15
MARGE_RANG = 0.5
DECALAGE_LEGENDE = (10, 10)
MODES = ((True, "avec régulation"), (False, "sans régulation"))


class PanneauStats(QWidget):
    """Statistiques lues en base par le serveur, à la demande.

    La supervision ne parle jamais à la base : « Actualiser » émet `actualisation_demandee`,
    la fenêtre envoie un STATS_DEMANDE au serveur, et la réponse revient par afficher().
    Le premier graphique montre chaque traversée de VP, avec ou sans régulation ; un
    résumé donne la moyenne de chaque mode et le gain. Le second montre la densité de
    chaque branche dans le temps.

    Signals:
        actualisation_demandee (): l'utilisateur veut des statistiques à jour.
    """

    actualisation_demandee = pyqtSignal()

    def __init__(self, libelles: dict[str, str], parent: QWidget | None = None) -> None:
        """Construit l'onglet, vide jusqu'à la première réponse.

        Args:
            libelles (dict[str, str]): nom de rue de chaque branche, par identifiant, dans l'ordre des branches.
            parent (QWidget | None): widget parent.
        """
        super().__init__(parent)
        self.__libelles = dict(libelles)
        self.__bouton = QPushButton("Actualiser")
        self.__etat = QLabel("Cliquez sur « Actualiser » pour lire les statistiques du serveur.")
        self.__resume = QLabel()
        self.__traversees = pg.PlotWidget()
        self.__densites = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.__preparer_graphiques()
        self.__disposer()
        self.__bouton.clicked.connect(self.actualisation_demandee)

    @property
    def bouton(self) -> QPushButton:
        """QPushButton: bouton « Actualiser »."""
        return self.__bouton

    @property
    def etat(self) -> QLabel:
        """QLabel: provenance des statistiques affichées, ou raison de leur absence."""
        return self.__etat

    @property
    def resume(self) -> QLabel:
        """QLabel: temps moyen de traversée avec et sans régulation, et le gain."""
        return self.__resume

    @property
    def traversees(self) -> pg.PlotWidget:
        """pg.PlotWidget: une marque par traversée de VP."""
        return self.__traversees

    @property
    def densites(self) -> pg.PlotWidget:
        """pg.PlotWidget: une courbe par branche."""
        return self.__densites

    def afficher(self, statistiques: dict) -> None:
        """Affiche une réponse STATS_REPONSE.

        Args:
            statistiques (dict): données de la réponse, avec `disponible` à False si la base est injoignable.
        """
        heure = datetime.now().time().isoformat(timespec="seconds")
        if not statistiques.get("disponible"):
            raison = statistiques.get("raison", "raison inconnue")
            self.__etat.setText(f"{heure} : statistiques indisponibles, {raison}")
            return
        passages, releves = statistiques["passages"], statistiques["densites"]
        self.__etat.setText(f"{heure} : {len(passages)} traversée(s) de VP et {len(releves)} relevé(s) de densité")
        self.__tracer_traversees(passages)
        self.__tracer_densites(releves)

    def __tracer_traversees(self, passages: list[dict]) -> None:
        """Une marque par traversée, dans l'ordre chronologique, couleur selon la régulation."""
        self.__traversees.clear()
        moyennes = {}
        for (regulation, nom), couleur in zip(MODES, COULEURS_SERIES):
            rangs = [rang + 1 for rang, passage in enumerate(passages) if passage["regulation"] is regulation]
            durees = [passage["duree"] for passage in passages if passage["regulation"] is regulation]
            self.__traversees.plot(
                rangs, durees, pen=None, name=nom, symbol="o", symbolSize=TAILLE_POINT,
                symbolBrush=couleur, symbolPen=pg.mkPen(COULEUR_FOND_GRAPHIQUE, width=EPAISSEUR_LIGNE),
            )
            moyennes[regulation] = (sum(durees) / len(durees), len(durees)) if durees else None
        self.__resume.setText(self.__resumer(moyennes))
        # Les durées partent de zéro, pour que l'écart entre les deux modes se lise à sa vraie taille.
        plus_longue = max((passage["duree"] for passage in passages), default=1.0)
        self.__traversees.setYRange(0, plus_longue * MARGE_HAUT)
        self.__traversees.setXRange(1 - MARGE_RANG, max(len(passages), 1) + MARGE_RANG)

    def __tracer_densites(self, releves: list[dict]) -> None:
        """Une courbe par branche : densité en pourcentage selon l'heure du relevé."""
        self.__densites.clear()
        for rang, (branche, libelle) in enumerate(self.__libelles.items()):
            points = [releve for releve in releves if releve["branche"] == branche]
            instants = [datetime.fromisoformat(releve["instant"]).timestamp() for releve in points]
            valeurs = [releve["densite"] * POURCENT for releve in points]
            couleur = COULEURS_SERIES[rang % len(COULEURS_SERIES)]
            self.__densites.plot(instants, valeurs, name=libelle, pen=pg.mkPen(couleur, width=EPAISSEUR_LIGNE))

    @staticmethod
    def __resumer(moyennes: dict[bool, tuple[float, int] | None]) -> str:
        """Écrit les temps moyens de traversée et, si les deux modes ont été mesurés, le gain."""
        morceaux = []
        for regulation, nom in MODES:
            mesure = moyennes[regulation]
            if mesure is None:
                morceaux.append(f"{nom} : aucune mesure")
            else:
                moyenne = PanneauStats.__en_francais(mesure[0])
                morceaux.append(f"{nom} : {moyenne} s en moyenne sur {mesure[1]} traversée(s)")
        resume = " ; ".join(morceaux)
        if moyennes[True] is not None and moyennes[False] is not None:
            gain = (1 - moyennes[True][0] / moyennes[False][0]) * POURCENT
            resume += f" ; gain : {gain:.0f} %"
        return "Temps de traversée du VP, " + resume

    @staticmethod
    def __en_francais(valeur: float) -> str:
        """Écrit un nombre à une décimale, avec la virgule décimale."""
        return f"{valeur:.1f}".replace(".", ",")

    def __preparer_graphiques(self) -> None:
        """Fond, axes, légende et grille discrète des deux graphiques."""
        for graphique, titre, axe_y, axe_x in (
            (self.__traversees, "Temps de traversée du VP", "durée (s)", "traversée n°"),
            (self.__densites, "Densité des branches", "densité (%)", "heure"),
        ):
            graphique.setBackground(COULEUR_FOND_GRAPHIQUE)
            graphique.setTitle(titre, color=COULEUR_TEXTE.name())
            graphique.setLabel("left", axe_y)
            graphique.setLabel("bottom", axe_x)
            graphique.showGrid(x=False, y=True, alpha=OPACITE_GRILLE)
            graphique.addLegend(offset=DECALAGE_LEGENDE)
        self.__densites.setYRange(0, POURCENT)
        # Une traversée porte un numéro entier : pas de graduation entre deux.
        self.__traversees.getAxis("bottom").setTickSpacing(1, 1)

    def __disposer(self) -> None:
        """Le bouton et l'état en haut, puis le résumé et les deux graphiques côte à côte."""
        haut = QHBoxLayout()
        haut.addWidget(self.__bouton)
        haut.addWidget(self.__etat, 1)
        graphiques = QHBoxLayout()
        graphiques.addWidget(self.__traversees, 1)
        graphiques.addWidget(self.__densites, 1)
        disposition = QVBoxLayout(self)
        disposition.addLayout(haut)
        disposition.addWidget(self.__resume)
        disposition.addLayout(graphiques, 1)
