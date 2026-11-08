import { ref, shallowRef, watch, type Ref, type ShallowRef, type WatchSource } from 'vue'

export interface Loaded<T> {
  data: ShallowRef<T | null>
  error: Ref<string | null>
  loading: Ref<boolean>
  reload: () => void // run `load` again now, e.g. a retry after an error
}

/**
 * Runs `load` now and again whenever a `deps` source changes, exposing data/error/loading.
 *
 * A slower earlier response never overwrites a newer one. `load` returning null clears the data
 * (nothing to fetch). `data` is a shallowRef: responses are replaced whole, never mutated, and
 * a deep proxy over thousands of rows is wasted work.
 */
export function useLoad<T>(load: () => Promise<T> | null, deps: WatchSource[] = []): Loaded<T> {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  let request = 0

  async function run(): Promise<void> {
    const mine = ++request
    error.value = null
    const pending = load()
    if (!pending) {
      data.value = null
      loading.value = false
      return
    }
    loading.value = true
    try {
      const result = await pending
      if (mine === request) data.value = result
    } catch (e) {
      if (mine === request) {
        data.value = null
        error.value = e instanceof Error ? e.message : String(e)
      }
    } finally {
      if (mine === request) loading.value = false
    }
  }

  watch(deps, run, { immediate: true })
  return { data, error, loading, reload: () => void run() }
}
