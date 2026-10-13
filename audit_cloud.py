import psycopg2
from psycopg2.extras import RealDictCursor

# 🟢 TON LIEN DE CONNEXION EXTERNE RENDER POSTGRESQL
URL_POSTGRES = "postgresql://serges_admin:TT7zdoWF9BYDHhPR3uPSRmpCi6CnFn88@dpg-db21lijncjis73bcau60-a.oregon-postgres.render.com/kashflow_db_gydg"

def console_superviseur_distant():
    print("\n====================================================")
    print("📡 KASHKEEPER CLOUD HUB - CONSOLE COMPTOIR DISTANTE")
    print("====================================================\n")
    
    try:
        conn = psycopg2.connect(URL_POSTGRES, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        # À insérer dans audit_cloud.py pour nettoyer la base PostgreSQL :
        cur.execute("DELETE FROM abonnements_magasin WHERE cle_boutique IN ('SERGE_TECH_998877', 'BOUTIQUE_1');")
        conn.commit()

      
        # 🟢 CORRIGÉ : On sécurise la lecture des caissières si aucune vente n'existe encore
        liste_caissieres = []
        try:
            cur.execute("SELECT DISTINCT caissiere FROM ventes_cloud_gerant;")
            liste_caissieres = [row["caissiere"].strip().lower() for row in cur.fetchall()]
        except Exception:
            conn.rollback() # Réinitialise la transaction PostgreSQL après l'absence de table
            print("📋 Statut : La table 'ventes_cloud_gerant' est en attente du tout premier ticket de caisse.")

        if not liste_caissieres:
            print("📋 Statut : Aucune caissière n'a encore envoyé de vente sur le Cloud.")
            cur.close(); conn.close()
            return
            
        print(f"👥 Caissières détectées en activité sur le réseau : {', '.join([c.upper() for c in liste_caissieres])}")
        
        # 2. Demande interactive à Serge
        cible = input("\n👉 Entrez le nom de la caissière à auditer (ou appuyez sur Entrée pour TOUT voir) : ").strip().lower()
        
        if cible and cible not in liste_caissieres:
            print(f"❌ Erreur : '{cible.upper()}' n'a aucune transaction enregistrée sur le serveur Cloud.")
            cur.close(); conn.close()
            return
            
        # 3. Extraction et calcul en direct du Chiffre d'Affaires Cloud
        if cible:
            cur.execute("""
                SELECT id_local, client, article, total_ttc, date_vente 
                FROM ventes_cloud_gerant 
                WHERE LOWER(caissiere) = %s 
                ORDER BY id_local DESC;
            """, (cible,))
            titre = f"📊 REGISTRE DES ENCAISSEMENTS EN DIRECT DE : {cible.upper()}"
        else:
            cur.execute("""
                SELECT id_local, client, article, total_ttc, date_vente, caissiere 
                FROM ventes_cloud_gerant 
                ORDER BY date_vente DESC, id_local DESC;
            """,)
            titre = "📊 TOTALITÉ DES VENTES DU RÉSEAU KASHKEEPER CLOUD"
            
        ventes = cur.fetchall()
        
        print(f"\n{titre}")
        print("-" * 75)
        print(f"{'N° FACTURE':<12} | {'CLIENT':<12} | {'MARCHANDISES':<22} | {'NET TTC':<12} | {'DATE/HEURE'}")
        print("-" * 75)
        
        total_ca_cumule = 0.0
        for v in ventes:
            num_f = f"#{str(v['id_local']).zfill(4)}"
            client = str(v['client']).upper()[:12]
            article = str(v['article']).upper()[:22]
            prix = float(v['total_ttc'])
            date_v = v['date_vente']
            
            # Si on affiche tout, on rajoute le nom de l'émetteur à côté de la date
            info_tempo = f"{date_v} ({v['caissiere'].upper()})" if not cible else date_v
            
            print(f"{num_f:<12} | {client:<12} | {article:<22} | {prix:,.0f} FCFA  | {info_tempo}")
            total_ca_cumule += prix
            
        print("-" * 75)
        print(f"💰 CHIFFRE D'AFFAIRES TOTAL ENCAISSÉ SUR LE CLOUD : {total_ca_cumule:,} FCFA")
        print("-" * 75)
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erreur d'antenne Cloud : {e}")

if __name__ == "__main__":
    console_superviseur_distant()
