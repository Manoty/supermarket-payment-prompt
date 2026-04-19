// frontend/src/pages/PaymentPage.jsx

import { useState } from 'react'
import { usePayment } from '../hooks/usePayment'

export default function PaymentPage() {
  const [phoneNumber, setPhoneNumber] = useState('')
  const [amount, setAmount] = useState('')
  const { status, transaction, errorMessage, initiatePayment, reset } = usePayment()

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!phoneNumber || !amount) return
    initiatePayment(phoneNumber, amount)
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-md p-8">

        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-4xl mb-2">🛒</div>
          <h1 className="text-2xl font-bold text-gray-800">CleanShelf Mart</h1>
          <p className="text-gray-500 text-sm mt-1">Secure M-Pesa Payment</p>
        </div>

        {/* IDLE / FORM */}
        {(status === 'idle' || status === 'error') && (
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phone Number
              </label>
              <input
                type="tel"
                placeholder="07XXXXXXXX or 254XXXXXXXXX"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Amount (KES)
              </label>
              <input
                type="number"
                placeholder="Enter amount"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                min="1"
                max="150000"
                className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                required
              />
            </div>

            {/* Error message */}
            {status === 'error' && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">
                {errorMessage}
              </div>
            )}

            <button
              type="submit"
              className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg transition-colors"
            >
              Pay with M-Pesa
            </button>
          </form>
        )}

        {/* LOADING — waiting for API response */}
        {status === 'loading' && (
          <div className="text-center py-8">
            <div className="animate-spin text-4xl mb-4">⏳</div>
            <p className="text-gray-600 font-medium">Sending payment request...</p>
          </div>
        )}

        {/* PENDING — STK push sent, waiting for user to enter PIN */}
        {status === 'pending' && (
          <div className="text-center py-8">
            <div className="text-5xl mb-4 animate-pulse">📱</div>
            <h2 className="text-lg font-semibold text-gray-800 mb-2">
              Check Your Phone
            </h2>
            <p className="text-gray-500 text-sm mb-6">
              An M-Pesa prompt has been sent to{' '}
              <span className="font-medium text-gray-700">{phoneNumber}</span>.
              Enter your PIN to complete the payment.
            </p>
            <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-bounce" />
              <div className="w-2 h-2 bg-green-400 rounded-full animate-bounce delay-100" />
              <div className="w-2 h-2 bg-green-400 rounded-full animate-bounce delay-200" />
              <span className="ml-1">Waiting for confirmation...</span>
            </div>
          </div>
        )}

        {/* SUCCESS */}
        {status === 'success' && (
          <div className="text-center py-8">
            <div className="text-5xl mb-4">✅</div>
            <h2 className="text-xl font-bold text-green-600 mb-2">
              Payment Successful!
            </h2>
            <p className="text-gray-500 text-sm mb-4">
              Thank you for your payment.
            </p>
            {transaction?.mpesa_receipt_number && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                <p className="text-xs text-gray-500 mb-1">M-Pesa Receipt</p>
                <p className="font-mono font-bold text-green-700 text-lg">
                  {transaction.mpesa_receipt_number}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  KES {transaction.amount}
                </p>
              </div>
            )}
            <button
              onClick={reset}
              className="w-full border border-gray-300 text-gray-600 font-medium py-3 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Make Another Payment
            </button>
          </div>
        )}

        {/* FAILED / CANCELLED / TIMEOUT */}
        {status === 'failed' && (
          <div className="text-center py-8">
            <div className="text-5xl mb-4">❌</div>
            <h2 className="text-xl font-bold text-red-600 mb-2">
              Payment Failed
            </h2>
            <p className="text-gray-500 text-sm mb-6">
              {errorMessage || 'Your payment could not be completed. Please try again.'}
            </p>
            <button
              onClick={reset}
              className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        )}

      </div>
    </div>
  )
}