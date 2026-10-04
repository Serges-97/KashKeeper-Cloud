# =====================================================================
# ENGINE FINANCIER KASHFLOW - MODULE 2 : operation.py (Étape 1 sur 3)
# =====================================================================
import os
import sys
from fpdf import FPDF
from datetime import datetime

# Taux officiel de la TVA en vigueur au Cameroun (19.25%)
TAUX_TVA_CAMEROUN = 19.25 / 100

def calculer_facture_dynamique(prix_unitaire_ht, quantite, applique_tva):
    """
    Calcule le montant Hors Taxes, la valeur exacte de la TVA (0% ou 19.25%)
    et le montant toutes taxes comprises (TTC) pour chaque ligne de facture.
    """
    try:
        prix = float(prix_unitaire_ht)
        qt = int(quantite)
        
        if prix <= 0 or qt <= 0:
            return None
            
        montant_ht = prix * qt
        
        if int(applique_tva) == 1:
            valeur_tva = montant_ht * TAUX_TVA_CAMEROUN
        else:
            valeur_tva = 0.0
            
        montant_ttc = montant_ht + valeur_tva
        
        return {
            "montant_ht": round(montant_ht, 2),
            "valeur_tva": round(valeur_tva, 2),
            "total_ttc": round(montant_ttc, 2)
        }
    except Exception:
        return None

def calculer_totaux_panier_global(liste_articles_panier):
    """Effectue la sommation comptable de toutes les lignes cumulées dans le panier."""
    global_ht = 0.0
    global_tva = 0.0
    global_ttc = 0.0
    
    for item in liste_articles_panier:
        global_ht += float(item["montant_ht"])
        global_tva += float(item["valeur_tva"])
        global_ttc += float(item["total_ttc"])
        
    return {
        "global_ht": round(global_ht, 2),
        "global_tva": round(global_tva, 2),
        "global_ttc": round(global_ttc, 2)
    }
# =====================================================================
# ENGINE FINANCIER KASHFLOW - MODULE 2 : operation.py (Étape 2 sur 3)
# =====================================================================
def generer_recu_pdf_industriel(nom_boutique, num_facture, nom_client, telephone_client, liste_articles_panier, nom_caissiere, global_ht, global_tva, global_ttc):
    """
    📄 INNOVATION DEMI-FORMAT A5 HAUTE CLARTÉ MULTI-ARTICLES :
    Génère un reçu au format compact A5 supportant l'affichage de plusieurs produits.
    """
    try:
        maintenant = datetime.now()
        date_facture = maintenant.strftime("%d/%m/%Y")
        heure_facture = maintenant.strftime("%H:%M")
        
        # Initialisation en format A5 (Demi-page)
        pdf = FPDF(orientation="P", unit="mm", format="A5")
        pdf.add_page()
        pdf.set_margins(10, 10, 10)
        
        # =====================================================================
        # 🛡️ 1. FILIGRANE DE SÉCURITÉ (LISIBILITÉ AMÉLIORÉE)
        # =====================================================================
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(242, 242, 242)
        pdf.text(x=12, y=95, txt=f"{nom_boutique.upper()} - DOCUMENT AUTHENTIQUE")
        pdf.text(x=12, y=103, txt="GARANTIE CONSTRUCTEUR CERTIFIEE")
        pdf.set_text_color(0, 0, 0)
        
        # =====================================================================
        # 🏢 2. EN-TÊTE OFFICIEL DE L'ENTREPRISE (CONTRASTE MAXIMAL)
        # =====================================================================
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(11, 92, 86) # Vert teal sombre anti-flou
        pdf.cell(128, 6, f"{nom_boutique.upper()}", ln=1, align="C")
        
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 23, 42) # Noir profond
        pdf.cell(128, 5, f"FACTURE COMMERCIALE N°{str(num_facture).zfill(4)}", ln=1, align="C")
        
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(51, 65, 85)
        pdf.cell(128, 4, f"Émise le {date_facture} à {heure_facture}", ln=1, align="C")
        pdf.ln(2)
        
        # Ligne de séparation renforcée
        pdf.set_draw_color(148, 163, 184)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 138, pdf.get_y())
        pdf.ln(3)
        
        # =====================================================================
        # 🧑‍💼 3. TRAÇABILITÉ DES ACTEURS
        # =====================================================================
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(64, 5, f"Client : {nom_client.upper()} ", ln=0)
        pdf.cell(64, 5, f"Émis par : {nom_caissiere.upper()}", ln=1, align="R")
        pdf.ln(3)
# =====================================================================
# ENGINE FINANCIER KASHFLOW - MODULE 2 : operation.py (Étape 3 sur 3)
# =====================================================================
        # =====================================================================
        # 📦 4. GRILLE DES ARTICLES MULTIPLES (POLICES ÉPAISSIES ANTI-FLOU)
        # =====================================================================
        pdf.set_fill_color(226, 232, 240)
        pdf.set_draw_color(148, 163, 184)
        pdf.set_font("Helvetica", "B", 8.5)
        
        # En-têtes des colonnes de la grille
        pdf.cell(53, 6, " DÉSIGNATION (IMEI/SERIE...)", border=1, ln=False, fill=True)
        pdf.cell(12, 6, "QTÉ", border=1, ln=False, align="C", fill=True)
        pdf.cell(31, 6, "P.U HT", border=1, ln=False, align="R", fill=True)
        pdf.cell(32, 6, "TOTAL TTC ", border=1, ln=True, align="R", fill=True)
        
        pdf.set_text_color(15, 23, 42)
        
        # Parcours dynamique du panier pour insérer chaque produit sur une ligne dédiée
        for item in liste_articles_panier:
            y_actuel = pdf.get_y()
            pdf.rect(10, y_actuel, 53, 9)
            pdf.set_xy(11, y_actuel + 0.5)
            
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(52, 4, str(item["article"]).upper(), ln=True)
            pdf.set_xy(11, pdf.get_y())
            pdf.set_font("Helvetica", "B", 7)
            pdf.cell(52, 4, f"IMEI: {item['description_unique']}", ln=False)
            
            # Injection des cellules financières associées à l'article
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_xy(63, y_actuel)
            pdf.cell(12, 9, f"{item['quantite']}", border=1, align="C")
            
            pu_ht = float(item["montant_ht"]) / int(item["quantite"])
            pdf.cell(31, 9, f"{pu_ht:,.0f} F", border=1, align="R")
            pdf.cell(32, 9, f"{item['total_ttc']:,.0f} F ", border=1, align="R", ln=True)
            
        pdf.ln(2)
        
        # =====================================================================
        # 📊 5. BLOC DES TOTAUX FINANCIERS CUMULÉS
        # =====================================================================
        pdf.set_x(65)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(38, 4, "Total Général HT :", ln=False, align="R")
        pdf.cell(25, 4, f"{global_ht:,.0f} FCFA", ln=True, align="R")
        
        pdf.set_x(65)
        pdf.cell(38, 4, "Total TVA Cumulée :", ln=False, align="R")
        pdf.cell(25, 4, f"{global_tva:,.0f} FCFA", ln=True, align="R")
        
        pdf.ln(1)
        pdf.set_x(55)
        pdf.set_fill_color(220, 252, 231) # Vert d'encadré Net à Payer contrasté
        pdf.set_draw_color(34, 197, 94)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(21, 128, 61) # Vert foncé net
        pdf.cell(73, 8, f" NET À PAYER : {global_ttc:,.0f} FCFA ", border=1, ln=True, align="C", fill=True)
        
        # =====================================================================
        # 📜 6. PIED DE PAGE ANTI-FATIGUE VISUELLE
        # =====================================================================
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(128, 4, "Merci pour votre confiance et a tres bientot !", ln=1, align="C")
        
        # =====================================================================
        # 📂 COORDONNÉES COMPTABLES DU SOUS-DOSSIER FACTURES_EMISES (FIXÉ .EXE)
        # =====================================================================
        if getattr(sys, 'frozen', False):
            dossier_exe = os.path.dirname(sys.executable)
        else:
            dossier_exe = os.path.dirname(os.path.abspath(__file__))
            
        dossier_factures = os.path.join(dossier_exe, "factures_emises")
        if not os.path.exists(dossier_factures):
            os.makedirs(dossier_factures, exist_ok=True)
            
        chemin_final_pdf = os.path.join(dossier_factures, f"Facture_{num_facture}.pdf")
        pdf.output(chemin_final_pdf)
        return True
    except Exception as err:
        print(f"[CRASH ECOUTE D'EDITION PDF] : {err}")
        return False

def generer_facture_gros_pdf_industriel(nom_boutique, num_facture, nom_client, liste_panier, caissiere_nom, general_ht, general_tva, general_ttc):
    """
    Génère un reçu PDF au format Facture de Gros (A5 Paysage ou Vertical standard) 
    dans le dossier 'factures_emises' avec un tableau multi-lignes complet.
    """
    import os
    from reportlab.lib.pagesizes import A5
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    # 📁 SÉCURITÉ CONSTRUCTEUR : Création automatique du dossier s'il n'existe pas
    dossier_factures = "factures_emises"
    if not os.path.exists(dossier_factures):
        os.makedirs(dossier_factures)

    nom_fichier = os.path.join(dossier_factures, f"Facture_Gros_{num_facture}.pdf")
    doc = SimpleDocTemplate(nom_fichier, pagesize=A5, rightMargin=20, leftMargin=20, topMargin=15, bottomMargin=15)
    
    elements = []
    styles = getSampleStyleSheet()

    # Styles personnalisés
    style_titre = ParagraphStyle('TitreBoutique', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#0f766e'), alignment=1)
    style_info = ParagraphStyle('InfoClient', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14)
    style_entete_tab = ParagraphStyle('EnteteTab', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=1)
    style_cellule = ParagraphStyle('CelluleTab', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=1)
    style_cellule_gauche = ParagraphStyle('CelluleTabG', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=0)
    style_total = ParagraphStyle('TotalTab', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, alignment=1)

    # En-tête de la facture
    elements.append(Paragraph(str(nom_boutique).upper(), style_titre))
    elements.append(Spacer(1, 10))
    
    date_facture = datetime.now().strftime("%d/%m/%Y à %H:%M")
    info_texte = f"<b>FACTURE EN GROS N° :</b> #{str(num_facture).zfill(4)}<br/>" \
                 f"<b>Date :</b> {date_facture}<br/>" \
                 f"<b>Client :</b> {str(nom_client).upper()}<br/>" \
                 f"<b>Émise par :</b> {str(caissiere_nom).upper()}"
    elements.append(Paragraph(info_texte, style_info))
    elements.append(Spacer(1, 15))

    # 📊 CONSTRUCTION DU TABLEAU MULTI-LINES
    # En-têtes du tableau demandés
    donnees_tableau = [[
        Paragraph("CAISSIÈRE", style_entete_tab),
        Paragraph("ARTICLE", style_entete_tab),
        Paragraph("QTE", style_entete_tab),
        Paragraph("P.U HT", style_entete_tab),
        Paragraph("TOT HT", style_entete_tab),
        Paragraph("TAUX TVA", style_entete_tab),
        Paragraph("MNT TVA", style_entete_tab),
        Paragraph("TOT TTC", style_entete_tab)
    ]]

    # Injection dynamique de chaque article du panier
    for item in liste_panier:
        taux_tva_txt = "19.25%" if item["tva_appliquee"] == 1 else "0%"
        donnees_tableau.append([
            Paragraph(str(caissiere_nom).upper(), style_cellule),
            Paragraph(str(item["article"]).upper(), style_cellule_gauche),
            Paragraph(f"{item['quantite']}", style_cellule),
            Paragraph(f"{item['prix_unitaire']:,} F", style_cellule),
            Paragraph(f"{item['total_ht']:,} F", style_cellule),
            Paragraph(taux_tva_txt, style_cellule),
            Paragraph(f"{item['total_tva']:,} F", style_cellule),
            Paragraph(f"{item['total_ttc']:,} F", style_cellule)
        ])

    # 🟢 AJOUT DE LA DERNIÈRE LIGNE DES TOTALS CUMULÉS
    donnees_tableau.append([
        Paragraph("<b>TOTAL GÉNÉRAL</b>", style_total),
        Paragraph("", style_total),
        Paragraph("", style_total),
        Paragraph("", style_total),
        Paragraph(f"<b>{general_ht:,} F</b>", style_total),
        Paragraph("", style_total),
        Paragraph(f"<b>{general_tva:,} F</b>", style_total),
        Paragraph(f"<b>{general_ttc:,} F</b>", style_total)
    ])

    # Configuration des largeurs de colonnes (Total 375 points pour le format A5 disponible)
    largeurs = [65, 85, 30, 45, 50, 45, 50, 55]
    
    tableau = Table(donnees_tableau, colWidths=largeurs)
    
    # Style visuel du tableau (Graphisme épuré et Pro)
    style_visuel = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        # Style spécifique pour la ligne des totaux (fond gris clair et lignes doubles)
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#0f766e')),
        ('SPAN', (0, -1), (3, -1)), # On fusionne les 4 premières cellules pour écrire "TOTAL GÉNÉRAL"
    ])
    
    tableau.setStyle(style_visuel)
    elements.append(tableau)
    
    # Génération physique
    doc.build(elements)
