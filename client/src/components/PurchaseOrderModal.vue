<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'create' ? t('purchaseOrder.createTitle') : t('purchaseOrder.viewTitle') }}
            </h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <!-- Backlog item context -->
            <div class="context-section">
              <div class="context-grid">
                <div class="context-item">
                  <span class="context-label">{{ t('purchaseOrder.orderId') }}</span>
                  <span class="context-value mono">{{ backlogItem.order_id }}</span>
                </div>
                <div class="context-item">
                  <span class="context-label">{{ t('purchaseOrder.sku') }}</span>
                  <span class="context-value mono">{{ backlogItem.item_sku }}</span>
                </div>
                <div class="context-item">
                  <span class="context-label">{{ t('purchaseOrder.itemName') }}</span>
                  <span class="context-value">{{ backlogItem.item_name }}</span>
                </div>
                <div class="context-item">
                  <span class="context-label">{{ t('purchaseOrder.shortage') }}</span>
                  <span class="context-value shortage-value">{{ shortage }} units</span>
                </div>
              </div>
            </div>

            <!-- Create mode: form -->
            <template v-if="mode === 'create'">
              <div class="form-section">
                <div class="form-group">
                  <label for="po-supplier-name">{{ t('purchaseOrder.supplierName') }} *</label>
                  <input
                    id="po-supplier-name"
                    v-model="form.supplier_name"
                    type="text"
                    class="form-input"
                    :placeholder="t('purchaseOrder.supplierNamePlaceholder')"
                  />
                </div>

                <div class="form-row">
                  <div class="form-group">
                    <label for="po-quantity">{{ t('purchaseOrder.quantity') }} *</label>
                    <input
                      id="po-quantity"
                      v-model.number="form.quantity"
                      type="number"
                      min="1"
                      class="form-input"
                    />
                  </div>

                  <div class="form-group">
                    <label for="po-unit-cost">{{ t('purchaseOrder.unitCost') }} *</label>
                    <input
                      id="po-unit-cost"
                      v-model.number="form.unit_cost"
                      type="number"
                      min="0.01"
                      step="0.01"
                      class="form-input"
                      :placeholder="t('purchaseOrder.unitCostPlaceholder')"
                    />
                  </div>
                </div>

                <div class="form-group">
                  <label for="po-delivery-date">{{ t('purchaseOrder.expectedDelivery') }} *</label>
                  <input
                    id="po-delivery-date"
                    v-model="form.expected_delivery_date"
                    type="date"
                    class="form-input"
                  />
                </div>

                <div class="form-group">
                  <label for="po-notes">{{ t('purchaseOrder.notes') }}</label>
                  <textarea
                    id="po-notes"
                    v-model="form.notes"
                    class="form-textarea"
                    :placeholder="t('purchaseOrder.notesPlaceholder')"
                    rows="3"
                  ></textarea>
                </div>

                <div v-if="formError" class="form-error">{{ formError }}</div>
              </div>
            </template>

            <!-- View mode: PO details -->
            <template v-else>
              <div v-if="viewLoading" class="state-message">{{ t('common.loading') }}</div>
              <div v-else-if="viewError" class="state-message error">{{ viewError }}</div>
              <div v-else-if="poData" class="po-details">
                <div class="po-number-row">
                  <div class="po-number-info">
                    <span class="po-number-label">{{ t('purchaseOrder.poNumber') }}</span>
                    <span class="po-number-value">{{ poData.id }}</span>
                  </div>
                  <span class="status-badge" :class="getStatusClass(poData.status)">
                    {{ poData.status }}
                  </span>
                </div>

                <div class="details-grid">
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.supplierName') }}</span>
                    <span class="detail-value">{{ poData.supplier_name }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.quantity') }}</span>
                    <span class="detail-value">{{ poData.quantity }} units</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.unitCost') }}</span>
                    <span class="detail-value">{{ formatCurrency(poData.unit_cost) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.totalCost') }}</span>
                    <span class="detail-value total-cost-value">{{ formatCurrency(poData.quantity * poData.unit_cost) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.expectedDelivery') }}</span>
                    <span class="detail-value">{{ formatDate(poData.expected_delivery_date) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">{{ t('purchaseOrder.createdDate') }}</span>
                    <span class="detail-value">{{ formatDate(poData.created_date) }}</span>
                  </div>
                </div>

                <div v-if="poData.notes" class="notes-section">
                  <span class="detail-label">{{ t('purchaseOrder.notes') }}</span>
                  <p class="notes-text">{{ poData.notes }}</p>
                </div>
              </div>
            </template>
          </div>

          <div class="modal-footer">
            <button class="btn-secondary" @click="close">{{ t('common.close') }}</button>
            <button
              v-if="mode === 'create'"
              class="btn-primary"
              :disabled="saving"
              @click="handleSubmit"
            >
              {{ saving ? t('purchaseOrder.submitting') : t('purchaseOrder.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

const { t, currentLocale } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create'
  }
})

const emit = defineEmits(['close', 'po-created'])

// Create mode state
const form = ref({
  supplier_name: '',
  quantity: 0,
  unit_cost: '',
  expected_delivery_date: '',
  notes: ''
})
const saving = ref(false)
const formError = ref(null)

// View mode state
const poData = ref(null)
const viewLoading = ref(false)
const viewError = ref(null)

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

const resetState = () => {
  form.value = {
    supplier_name: '',
    quantity: shortage.value,
    unit_cost: '',
    expected_delivery_date: '',
    notes: ''
  }
  formError.value = null
  saving.value = false
  poData.value = null
  viewError.value = null
  viewLoading.value = false
}

const fetchPO = async () => {
  if (!props.backlogItem) return
  viewLoading.value = true
  viewError.value = null
  try {
    poData.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    if (err.response?.status === 404) {
      viewError.value = t('purchaseOrder.notFound')
    } else {
      viewError.value = t('purchaseOrder.fetchError')
    }
  } finally {
    viewLoading.value = false
  }
}

// Reset and fetch whenever the modal opens
watch(
  () => props.isOpen,
  (isOpen) => {
    if (isOpen) {
      resetState()
      if (props.mode === 'view') {
        fetchPO()
      }
    }
  }
)

const close = () => {
  emit('close')
}

const handleSubmit = async () => {
  if (!props.backlogItem) return

  // Client-side validation
  if (!form.value.supplier_name.trim()) {
    formError.value = t('purchaseOrder.supplierRequired')
    return
  }
  if (!form.value.quantity || form.value.quantity <= 0) {
    formError.value = t('purchaseOrder.quantityRequired')
    return
  }
  if (!form.value.unit_cost || form.value.unit_cost <= 0) {
    formError.value = t('purchaseOrder.unitCostRequired')
    return
  }
  if (!form.value.expected_delivery_date) {
    formError.value = t('purchaseOrder.deliveryDateRequired')
    return
  }

  saving.value = true
  formError.value = null

  try {
    const result = await api.createPurchaseOrder({
      backlog_item_id: props.backlogItem.id,
      supplier_name: form.value.supplier_name.trim(),
      quantity: form.value.quantity,
      unit_cost: form.value.unit_cost,
      expected_delivery_date: form.value.expected_delivery_date,
      notes: form.value.notes.trim() || null
    })
    emit('po-created', result)
  } catch (err) {
    if (err.response?.status === 409) {
      formError.value = t('purchaseOrder.alreadyExists')
    } else if (err.response?.status === 400) {
      formError.value = err.response.data?.detail || t('purchaseOrder.invalidData')
    } else {
      formError.value = t('purchaseOrder.submitError')
    }
  } finally {
    saving.value = false
  }
}

const getStatusClass = (status) => {
  const map = {
    'Pending': 'status-pending',
    'Approved': 'status-approved',
    'Delivered': 'status-delivered',
    'Cancelled': 'status-cancelled'
  }
  return map[status] || 'status-pending'
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  // Parse YYYY-MM-DD manually to construct a local-time Date.
  // new Date('YYYY-MM-DD') treats the string as UTC midnight, which renders
  // one day earlier in any negative-UTC-offset timezone (e.g. US Pacific = UTC-7/8).
  const parts = dateString.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!parts) return dateString
  const date = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
  const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
  return date.toLocaleDateString(locale, { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
  margin: 0;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.modal-footer {
  padding: 1.25rem 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  flex-shrink: 0;
}

/* Context section */
.context-section {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem 1.5rem;
}

.context-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.context-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.context-value {
  font-size: 0.9rem;
  color: #0f172a;
  font-weight: 500;
}

.context-value.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.context-value.shortage-value {
  color: #dc2626;
  font-weight: 700;
}

/* Form */
.form-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
}

.form-input,
.form-textarea {
  padding: 0.625rem 0.875rem;
  border: 1.5px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.9rem;
  color: #0f172a;
  font-family: inherit;
  transition: border-color 0.15s ease;
  background: white;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #64748b;
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-error {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 0.875rem;
  font-weight: 500;
}

/* PO details (view mode) */
.state-message {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.95rem;
}

.state-message.error {
  color: #dc2626;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
}

.po-details {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.po-number-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e2e8f0;
}

.po-number-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.po-number-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.po-number-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
  font-family: 'Monaco', 'Courier New', monospace;
}

.status-badge {
  font-size: 0.813rem;
  font-weight: 600;
  padding: 0.375rem 0.875rem;
  border-radius: 6px;
  letter-spacing: 0.025em;
}

.status-badge.status-pending {
  background: #fef3c7;
  color: #92400e;
}

.status-badge.status-approved {
  background: #dbeafe;
  color: #1e40af;
}

.status-badge.status-delivered {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.status-cancelled {
  background: #fecaca;
  color: #991b1b;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.detail-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.detail-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.detail-value.total-cost-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.notes-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.notes-text {
  margin: 0;
  font-size: 0.9rem;
  color: #334155;
  line-height: 1.6;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.875rem 1rem;
}

/* Buttons */
.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #0f172a;
  border: 1px solid #0f172a;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
  border-color: #1e293b;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
