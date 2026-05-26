<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Budget Card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetTitle') }}</h3>
          <button
            class="btn-primary"
            :disabled="submitting || includedItems.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div class="budget-slider-row">
          <label class="budget-label">{{ t('restocking.budgetLabel') }}</label>
          <!-- accent-color drives the thumb/fill color in modern browsers -->
          <input
            type="range"
            class="budget-slider"
            v-model.number="budget"
            :min="0"
            :step="500"
            :max="sliderMax"
          />
          <span class="budget-display">{{ formatCurrency(budget, currentCurrency) }}</span>
        </div>

        <div class="budget-stats">
          <div class="budget-stat">
            <div class="budget-stat-label">{{ t('restocking.budgetLabel') }}</div>
            <div class="budget-stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
          </div>
          <div class="budget-stat">
            <div class="budget-stat-label">{{ t('restocking.allocated') }}</div>
            <div class="budget-stat-value value-allocated">{{ formatCurrency(allocated, currentCurrency) }}</div>
          </div>
          <div class="budget-stat">
            <div class="budget-stat-label">{{ t('restocking.remaining') }}</div>
            <div class="budget-stat-value value-remaining">{{ formatCurrency(remaining, currentCurrency) }}</div>
          </div>
          <div class="budget-stat">
            <div class="budget-stat-label">{{ t('restocking.itemsSelected', { selected: includedItems.length, total: recommendations.length }) }}</div>
            <div class="budget-stat-value">{{ includedItems.length }} / {{ recommendations.length }}</div>
          </div>
        </div>

        <!-- Success banner: shown after a successful order; clears when slider moves -->
        <div v-if="submittedOrder" class="success-banner">
          <span>{{ t('restocking.orderSuccess', { orderNumber: submittedOrder.order_number }) }}</span>
          <router-link to="/orders" class="banner-link">{{ t('restocking.viewOrders') }}</router-link>
        </div>

        <!-- Order submission error -->
        <div v-if="orderError" class="error">{{ orderError }}</div>
      </div>

      <!-- Recommendations Card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationsTitle') }}</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.currentStock') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.shortfall') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <!--
                Row opacity dims excluded rows so the budget cutoff is immediately visible.
                The API returns recommendations pre-sorted by shortfall descending — we keep
                that order and apply the greedy allocation computed property.
              -->
              <tr
                v-for="rec in recommendations"
                :key="rec.sku"
                :class="{ 'row-excluded': !isIncluded(rec.sku) }"
              >
                <td><strong>{{ rec.sku }}</strong></td>
                <td>{{ rec.name }}</td>
                <td>{{ rec.category || '—' }}</td>
                <td>{{ rec.current_stock }}</td>
                <td>{{ rec.forecasted_demand }}</td>
                <td>{{ rec.shortfall_units }}</td>
                <td>{{ formatCurrency(rec.unit_cost, currentCurrency) }}</td>
                <td>{{ rec.recommended_quantity }}</td>
                <td>{{ formatCurrency(rec.line_cost, currentCurrency) }}</td>
                <td>{{ rec.lead_time_days }} days</td>
                <td>
                  <span v-if="isIncluded(rec.sku)" class="badge success">{{ t('restocking.included') }}</span>
                  <span v-else class="badge warning">{{ t('restocking.overBudget') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const recommendations = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const submittedOrder = ref(null)
    const orderError = ref(null)

    // sliderMax: total line_cost of ALL recommendations rounded UP to the nearest $1,000.
    // Derived after load so the range always covers the full order cost.
    const sliderMax = computed(() => {
      const total = recommendations.value.reduce((sum, r) => sum + r.line_cost, 0)
      return Math.ceil(total / 1000) * 1000
    })

    // Greedy whole-line budget allocation.
    // Walk recommendations in the API-provided order (largest shortfall first).
    // Include a row only if its FULL line_cost fits in the remaining budget — no
    // partial quantities allowed. An expensive top-of-list item can be skipped
    // while cheaper items below still fit; this is intentional and maximises the
    // number of distinct items purchased within the budget.
    const includedItems = computed(() => {
      let remaining = Number(budget.value)
      const included = []
      for (const rec of recommendations.value) {
        if (rec.line_cost <= remaining) {
          included.push(rec)
          remaining -= rec.line_cost
        }
        // If this item exceeds remaining budget, skip it and keep walking
      }
      return included
    })

    // Set of included SKUs for O(1) lookup in the template
    const includedSkus = computed(() => new Set(includedItems.value.map(r => r.sku)))

    const isIncluded = (sku) => includedSkus.value.has(sku)

    const allocated = computed(() => includedItems.value.reduce((sum, r) => sum + r.line_cost, 0))
    const remaining = computed(() => Number(budget.value) - allocated.value)

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockingRecommendations()
        recommendations.value = data
        // Default budget = half of sliderMax rounded down to the nearest step (500).
        // Computed inline here because sliderMax depends on recommendations.value
        // which we just set — Vue's synchronous computed update handles this.
        const max = Math.ceil(data.reduce((sum, r) => sum + r.line_cost, 0) / 1000) * 1000
        budget.value = Math.round(max / 2 / 500) * 500
      } catch (err) {
        error.value = 'Failed to load restocking recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Clear the success banner whenever the user adjusts the slider
    watch(budget, () => {
      submittedOrder.value = null
    })

    const placeOrder = async () => {
      if (submitting.value || includedItems.value.length === 0) return
      submitting.value = true
      orderError.value = null
      try {
        // The backend does not mutate inventory, so recommendations and the slider
        // are intentionally left unchanged after a successful order submission.
        // api.createRestockOrder already unwraps axios's response.data and returns the order object.
        const createdOrder = await api.createRestockOrder({
          budget: Number(budget.value),
          items: includedItems.value.map(r => ({ sku: r.sku, quantity: r.recommended_quantity }))
        })
        submittedOrder.value = createdOrder
      } catch (err) {
        orderError.value = 'Failed to place restock order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      t,
      currentCurrency,
      formatCurrency,
      loading,
      error,
      recommendations,
      budget,
      sliderMax,
      includedItems,
      isIncluded,
      allocated,
      remaining,
      submitting,
      submittedOrder,
      orderError,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-slider-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}

.budget-slider {
  flex: 1;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-display {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 110px;
  text-align: right;
}

.budget-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.budget-stat-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.25rem;
}

.budget-stat-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-stat-value.value-allocated {
  color: #2563eb;
}

.budget-stat-value.value-remaining {
  color: #059669;
}

.success-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-top: 0.75rem;
  font-size: 0.938rem;
  font-weight: 500;
}

.banner-link {
  color: #065f46;
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}

.banner-link:hover {
  color: #047857;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.5rem 1.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.restock-table {
  width: 100%;
}

/* Dim rows excluded by the budget cutoff so the included/excluded split is obvious */
.row-excluded {
  opacity: 0.4;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}
</style>
