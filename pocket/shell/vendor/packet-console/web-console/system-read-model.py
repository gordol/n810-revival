"""Pure projections of observed host resources and interface counters."""
import math
import time


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def difference(total, free):
    total, free = number(total), number(free)
    return total - free if total is not None and free is not None and free <= total else None


def delta(current, previous, key):
    a, b = number(current.get(key)), number(previous.get(key))
    return a - b if a is not None and b is not None and a >= b else None


def battery_rows(rows):
    result = []
    fields = {'POWER_SUPPLY_CAPACITY': 'capacity_percent',
              'POWER_SUPPLY_VOLTAGE_NOW': 'voltage_microvolts',
              'POWER_SUPPLY_CURRENT_NOW': 'current_microamps',
              'POWER_SUPPLY_TEMP': 'temperature_tenths_celsius'}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get('POWER_SUPPLY_TYPE') != 'Battery':
            continue
        item = {'name': row.get('POWER_SUPPLY_NAME'), 'status': row.get('POWER_SUPPLY_STATUS')}
        for key, target in fields.items():
            try:
                item[target] = int(row[key])
            except (KeyError, TypeError, ValueError):
                item[target] = None
        result.append(item)
    return result


def project(current, previous=None, now=None):
    """Project raw read-state samples; rates require a continuous same-boot window.

    Interface rates measure host-interface bytes, not radio capacity. CPU idle
    counters must already include iowait. Missing or invalid evidence stays None.
    """
    current = current or {}
    previous = previous or {}
    system = current.get('system') or {}
    old = previous.get('system') or {}
    now = time.time() if now is None else now
    observed = number(system.get('observed_at'))
    age = now - observed if observed is not None and number(now) is not None else None
    if age is not None and age < 0:
        age = None
    freshness = 'unavailable' if age is None else ('fresh' if age <= 120 else 'stale')
    duration = delta(system, old, 'uptime_seconds')
    prior_observed = number(old.get('observed_at'))
    boot_id = system.get('boot_id')
    continuous = bool(isinstance(boot_id, str) and boot_id.strip() and boot_id == old.get('boot_id')
                      and duration is not None and 0 < duration <= 120
                      and observed is not None and prior_observed is not None
                      and observed > prior_observed and freshness == 'fresh')
    cpu = system.get('cpu') or {}
    old_cpu = old.get('cpu') or {}
    total = delta(cpu, old_cpu, 'total_ticks')
    idle = delta(cpu, old_cpu, 'idle_ticks')
    busy = None
    if continuous and total is not None and total > 0 and idle is not None and idle <= total:
        busy = 100.0 * (total - idle) / total
    memory = system.get('memory_bytes') or {}
    swap = system.get('swap') or {}
    old_swap = old.get('swap') or {}
    swap_rates = {'in_bytes_per_second': None, 'out_bytes_per_second': None}
    page_size = number(swap.get('page_size_bytes'))
    if continuous and page_size is not None and page_size > 0 and page_size == number(old_swap.get('page_size_bytes')):
        for counter, output in [('in_pages', 'in_bytes_per_second'), ('out_pages', 'out_bytes_per_second')]:
            change = delta(swap, old_swap, counter)
            if change is not None:
                swap_rates[output] = change * page_size / duration
    interfaces = {}
    stats, old_stats = current.get('network_stats') or {}, previous.get('network_stats') or {}
    for name in sorted(set(stats) | set(old_stats)):
        row, prior = stats.get(name) or {}, old_stats.get(name) or {}
        rates = {'rx_bytes_per_second': None, 'tx_bytes_per_second': None}
        for key in ('rx_bytes', 'tx_bytes'):
            change = delta(row, prior, key)
            if continuous and change is not None:
                rates[key + '_per_second'] = change / duration
        interfaces[name] = rates
    load = system.get('load_average')
    if not isinstance(load, (list, tuple)) or len(load) != 3 or any(number(v) is None for v in load):
        load = None
    else:
        load = list(load)
    return {'source': system.get('source'), 'platform': system.get('platform'),
            'observed_at': observed, 'sample_age_seconds': age, 'freshness': freshness,
            'boot_id': system.get('boot_id'), 'uptime_seconds': number(system.get('uptime_seconds')),
            'rate_window_seconds': duration if continuous else None,
            'cpu_busy_percent': busy, 'load_average': load,
            'memory_used_bytes': difference(memory.get('total'), memory.get('available')),
            'memory_total_bytes': number(memory.get('total')),
            'memory_available_bytes': number(memory.get('available')),
            'memory_free_bytes': number(memory.get('free')),
            'swap_used_bytes': difference(swap.get('total_bytes'), swap.get('free_bytes')),
            'swap_total_bytes': number(swap.get('total_bytes')), 'swap': swap_rates,
            'network_interfaces': interfaces, 'batteries': battery_rows(current.get('power'))}
