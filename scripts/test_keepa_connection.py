#!/usr/bin/env python3
"""
Test de connexion à l'API Keepa
Vérifie que la clé API fonctionne et affiche les tokens disponibles.
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire racine au path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Charger les variables d'environnement
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import keepa


def test_keepa_connection():
    """Teste la connexion Keepa et affiche les infos du compte."""

    api_key = os.getenv("KEEPA_API_KEY")

    if not api_key:
        print("❌ ERREUR: KEEPA_API_KEY non trouvée dans .env")
        return False

    print("=" * 60)
    print("TEST DE CONNEXION KEEPA")
    print("=" * 60)
    print(f"Clé API: {api_key[:10]}...{api_key[-5:]}")
    print()

    try:
        # Initialiser le client Keepa
        api = keepa.Keepa(api_key)

        # Récupérer les infos du compte (tokens)
        tokens_left = api.tokens_left

        print(f"✅ CONNEXION RÉUSSIE!")
        print(f"   Tokens restants: {tokens_left}")
        print()

        # Test: récupérer un produit simple pour valider
        print("Test de récupération d'un produit...")
        test_asin = "B08L5TNJHG"  # Un car phone mount populaire

        products = api.query(test_asin, domain='US')

        if products:
            product = products[0]
            title = product.get('title', 'N/A')
            if title and len(title) > 50:
                title = title[:50] + "..."

            print(f"✅ PRODUIT RÉCUPÉRÉ!")
            print(f"   ASIN: {test_asin}")
            print(f"   Titre: {title}")
            print(f"   Tokens après requête: {api.tokens_left}")
        else:
            print(f"⚠️  Aucun produit trouvé pour {test_asin}")

        print()
        print("=" * 60)
        print("RÉSUMÉ")
        print("=" * 60)
        print(f"✅ API Keepa opérationnelle")
        print(f"✅ Tokens disponibles: {api.tokens_left}")
        print(f"✅ Prêt pour l'ingestion de données")

        return True

    except Exception as e:
        print(f"❌ ERREUR: {e}")
        print()
        print("Vérifiez:")
        print("  1. La clé API est correcte")
        print("  2. Vous avez un abonnement Keepa actif")
        print("  3. Votre connexion internet fonctionne")
        return False


if __name__ == "__main__":
    success = test_keepa_connection()
    sys.exit(0 if success else 1)
