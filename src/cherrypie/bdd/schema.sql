-- Historique du rond-point CherryPie, écrit par le serveur.
-- scripts/init_bdd.py exécute ce fichier ; il peut être relancé sans rien perdre.

CREATE TABLE IF NOT EXISTS passage_vp (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vp VARCHAR(64) NOT NULL,
    entree VARCHAR(64) NOT NULL,
    sortie VARCHAR(64) NOT NULL,
    debut DATETIME(3) NOT NULL,
    fin DATETIME(3) NOT NULL,
    duree DOUBLE NOT NULL,
    duree_anneau DOUBLE NULL,
    regulation BOOLEAN NOT NULL,
    densite_moyenne DOUBLE NOT NULL,
    INDEX (debut)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS releve_densite (
    id INT AUTO_INCREMENT PRIMARY KEY,
    instant DATETIME(3) NOT NULL,
    branche VARCHAR(64) NOT NULL,
    densite DOUBLE NOT NULL,
    INDEX (instant)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS evenement_connexion (
    id INT AUTO_INCREMENT PRIMARY KEY,
    instant DATETIME(3) NOT NULL,
    usager VARCHAR(64) NOT NULL,
    categorie VARCHAR(16) NOT NULL,
    evenement ENUM('connexion', 'deconnexion') NOT NULL,
    detail VARCHAR(255) NOT NULL,
    INDEX (instant)
) CHARACTER SET utf8mb4;
