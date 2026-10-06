/**
 * budget_realtime.js
 * Calculs en temps réel pour le formulaire de dépense
 * Gestion de l'interface utilisateur interactive
 */

(function() {
    'use strict';

    // ========================================
    // CONFIGURATION & CONSTANTES
    // ========================================
    const SELECTORS = {
        prixUnitaire: '#id_prix_unitaire',
        quantite: '#id_quantite',
        montantTotalPreview: '#montant-total-preview',
        montantTotalValue: '#montant-total-value',
        depenseForm: '#depense-form',
        submitBtn: '#depense-form button[type="submit"]'
    };

    const CURRENCY_LOCALE = 'fr-FR';
    const CURRENCY_OPTIONS = {
        style: 'currency',
        currency: 'MGA', // Ariary malgache
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    };

    // ========================================
    // UTILITAIRES
    // ========================================

    /**
     * Formate un nombre en devise (Ar - Ariary)
     * @param {number} value - Valeur à formater
     * @returns {string} - Chaîne formatée
     */
    function formatCurrency(value) {
        if (isNaN(value) || value === null || value === '') {
            return '0 Ar';
        }
        try {
            // Utiliser Intl.NumberFormat pour l'Ariary (MGA)
            return new Intl.NumberFormat(CURRENCY_LOCALE, {
                style: 'currency',
                currency: 'MGA',
                minimumFractionDigits: 0,
                maximumFractionDigits: 0
            }).format(value).replace('MGA', 'Ar').trim();
        } catch (e) {
            // Fallback si Intl n'est pas supporté
            return value.toLocaleString(CURRENCY_LOCALE, { minimumFractionDigits: 0 }) + ' Ar';
        }
    }

    /**
     * Parse une valeur de champ en nombre
     * @param {HTMLInputElement} input - Élément input
     * @returns {number} - Valeur numérique ou 0
     */
    function parseInputValue(input) {
        const value = parseFloat(input.value);
        return isNaN(value) ? 0 : value;
    }

    /**
     * Affiche/désactive l'indicateur de chargement sur un bouton
     * @param {HTMLButtonElement} btn - Bouton cible
     * @param {boolean} loading - État de chargement
     */
    function setButtonLoading(btn, loading) {
        if (!btn) return;

        if (loading) {
            btn.disabled = true;
            btn.classList.add('loading');
            btn.dataset.originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Enregistrement...';
        } else {
            btn.disabled = false;
            btn.classList.remove('loading');
            if (btn.dataset.originalText) {
                btn.innerHTML = btn.dataset.originalText;
            }
        }
    }

    /**
     * Valide le formulaire côté client
     * @param {HTMLFormElement} form - Formulaire à valider
     * @returns {boolean} - True si valide
     */
    function validateForm(form) {
        let isValid = true;
        const requiredFields = form.querySelectorAll('[required]');

        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                field.classList.add('is-invalid');
                isValid = false;
            } else {
                field.classList.remove('is-invalid');
            }
        });

        // Validation spécifique : prix > 0
        const prixInput = form.querySelector(SELECTORS.prixUnitaire);
        if (prixInput && parseInputValue(prixInput) <= 0) {
            prixInput.classList.add('is-invalid');
            isValid = false;
        }

        // Validation spécifique : quantité >= 1
        const quantiteInput = form.querySelector(SELECTORS.quantite);
        if (quantiteInput && parseInputValue(quantiteInput) < 1) {
            quantiteInput.classList.add('is-invalid');
            isValid = false;
        }

        return isValid;
    }

    // ========================================
    // LOGIQUE PRINCIPALE : CALCUL TEMPS RÉEL
    // ========================================

    /**
     * Met à jour l'affichage du montant total
     */
    function updateMontantTotal() {
        const prixInput = document.querySelector(SELECTORS.prixUnitaire);
        const quantiteInput = document.querySelector(SELECTORS.quantite);
        const montantValueEl = document.querySelector(SELECTORS.montantTotalValue);
        const montantPreviewEl = document.querySelector(SELECTORS.montantTotalPreview);

        if (!prixInput || !quantiteInput || !montantValueEl) return;

        const prix = parseInputValue(prixInput);
        const quantite = parseInputValue(quantiteInput);
        const total = prix * quantite;

        // Mise à jour de la valeur affichée
        montantValueEl.textContent = formatCurrency(total);

        // Changement de style selon le montant
        if (total > 0) {
            montantPreviewEl.classList.remove('alert-info');
            montantPreviewEl.classList.add('alert-success');
            montantValueEl.style.color = '#198754'; // Vert succès
        } else {
            montantPreviewEl.classList.remove('alert-success');
            montantPreviewEl.classList.add('alert-info');
            montantValueEl.style.color = '#0d6efd'; // Bleu primary
        }

        // Animation subtile
        montantValueEl.style.transform = 'scale(1.05)';
        setTimeout(() => {
            montantValueEl.style.transform = 'scale(1)';
        }, 150);
    }

    /**
     * Gestionnaire d'événements pour les inputs
     */
    function handleInputChange() {
        updateMontantTotal();
    }

    // ========================================
    // GESTION DU FORMULAIRE
    // ========================================

    /**
     * Initialise la validation et la soumission du formulaire
     */
    function initFormHandling() {
        const form = document.querySelector(SELECTORS.depenseForm);
        const submitBtn = document.querySelector(SELECTORS.submitBtn);

        if (!form) return;

        // Validation en temps réel
        form.querySelectorAll('input, select').forEach(input => {
            input.addEventListener('blur', () => {
                if (input.hasAttribute('required') && !input.value.trim()) {
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });

            input.addEventListener('input', () => {
                if (input.classList.contains('is-invalid') && input.value.trim()) {
                    input.classList.remove('is-invalid');
                }
            });
        });

        // Soumission du formulaire
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();

                // Scroll vers le premier champ invalide
                const firstInvalid = this.querySelector('.is-invalid');
                if (firstInvalid) {
                    firstInvalid.focus();
                    firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                return false;
            }

            // État de chargement
            setButtonLoading(submitBtn, true);
        });
    }

    // ========================================
    // AMÉLIORATIONS UX
    // ========================================

    /**
     * Focus automatique sur le premier champ du formulaire
     */
    function autoFocusFirstField() {
        const firstInput = document.querySelector(SELECTORS.depenseForm + ' input:not([type="hidden"]), ' + SELECTORS.depenseForm + ' select');
        if (firstInput && !firstInput.value) {
            firstInput.focus();
        }
    }

    /**
     * Gestion de la touche Entrée dans les champs numériques
     */
    function handleEnterKey() {
        document.querySelectorAll(SELECTORS.prixUnitaire + ', ' + SELECTORS.quantite).forEach(input => {
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const form = document.querySelector(SELECTORS.depenseForm);
                    if (form && validateForm(form)) {
                        form.submit();
                    }
                }
            });
        });
    }

    /**
     * Formatage automatique des nombres à la perte de focus
     */
    function initNumberFormatting() {
        document.querySelectorAll(SELECTORS.prixUnitaire + ', ' + SELECTORS.quantite).forEach(input => {
            input.addEventListener('blur', function() {
                const value = parseInputValue(this);
                if (value > 0) {
                    // Pour le prix, on garde 2 décimales
                    if (this.id === 'id_prix_unitaire') {
                        this.value = value.toFixed(2);
                    } else {
                        this.value = Math.floor(value);
                    }
                }
                updateMontantTotal();
            });
        });
    }

    /**
     * Confirmation de suppression (la confirmation HTML native est gérée
     * directement dans le template via l'attribut onsubmit).
     */
    /**
     * Animation d'apparition des lignes du tableau
     */
    function animateTableRows() {
        const rows = document.querySelectorAll('#depenses-table tbody tr');
        rows.forEach((row, index) => {
            row.style.opacity = '0';
            row.style.transform = 'translateY(10px)';
            row.style.transition = 'opacity 0.3s ease, transform 0.3s ease';

            setTimeout(() => {
                row.style.opacity = '1';
                row.style.transform = 'translateY(0)';
            }, 50 * index);
        });
    }

    /**
     * Tooltip pour les montants élevés
     */
    function initTooltips() {
        // Utiliser Bootstrap tooltips si disponible
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    /**
     * Gestion du responsive pour les cartes de budget
     */
    function handleResponsiveCards() {
        const cards = document.querySelectorAll('.budget-card');
        const checkCards = () => {
            cards.forEach(card => {
                if (window.innerWidth < 576) {
                    card.classList.add('border-start', 'border-primary', 'border-3');
                } else {
                    card.classList.remove('border-start', 'border-primary', 'border-3');
                }
            });
        };

        checkCards();
        window.addEventListener('resize', checkCards);
    }

    // ========================================
    // INITIALISATION
    // ========================================

    /**
     * Point d'entrée principal
     */
    function init() {
        // Attendre que le DOM soit prêt
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
            return;
        }

        console.log('[Budget App] Initialisation du module temps réel...');

        // Initialiser les écouteurs d'événements pour le calcul temps réel
        const prixInput = document.querySelector(SELECTORS.prixUnitaire);
        const quantiteInput = document.querySelector(SELECTORS.quantite);

        if (prixInput && quantiteInput) {
            // Événements pour le calcul en temps réel
            ['input', 'change', 'keyup'].forEach(eventType => {
                prixInput.addEventListener(eventType, handleInputChange);
                quantiteInput.addEventListener(eventType, handleInputChange);
            });

            // Calcul initial
            updateMontantTotal();
        }

        // Initialiser les autres modules
        initFormHandling();
        initNumberFormatting();
        autoFocusFirstField();
        handleEnterKey();
        animateTableRows();
        initTooltips();
        handleResponsiveCards();

        // Gestion des messages flash (auto-dismiss)
        document.querySelectorAll('.alert-dismissible').forEach(alert => {
            setTimeout(() => {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }, 5000);
        });

        console.log('[Budget App] Module temps réel initialisé avec succès.');
    }

    // ========================================
    // EXPORT POUR TESTS (optionnel)
    // ========================================
    window.BudgetApp = {
        formatCurrency,
        parseInputValue,
        updateMontantTotal,
        init
    };

    // Démarrer l'application
    init();

})();