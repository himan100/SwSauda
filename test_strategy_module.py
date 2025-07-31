#!/usr/bin/env python3
"""
Test script for the Strategy Module
This script tests the strategy creation, execution, and API endpoints
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import connect_to_mongo, close_mongo_connection, get_database
from models import (
    StrategyCreate, StrategyStep, StrategyCondition, StrategyAction,
    StrategyConditionType, StrategyActionType, StrategyStepType, StrategyStatus
)
from crud import create_strategy, get_strategies, get_strategy_by_id, update_strategy, delete_strategy

async def test_strategy_creation():
    """Test creating a simple trading strategy"""
    print("=== Testing Strategy Creation ===")
    
    # Create a simple EMA crossover strategy
    strategy_data = StrategyCreate(
        name="EMA Crossover Strategy",
        description="Simple EMA crossover strategy for NIFTY",
        status=StrategyStatus.ACTIVE,
        symbols=["NIFTY"],
        max_positions=2,
        risk_per_trade=2.0,
        is_active=True,
        steps=[
            StrategyStep(
                step_id="step_1",
                step_type=StrategyStepType.CONDITION,
                step_order=0,
                condition=StrategyCondition(
                    condition_type=StrategyConditionType.EMA_CROSSES_ABOVE,
                    symbol="NIFTY",
                    value=0,
                    description="Check if short EMA crosses above long EMA"
                ),
                description="Check EMA crossover condition"
            ),
            StrategyStep(
                step_id="step_2",
                step_type=StrategyStepType.ACTION,
                step_order=1,
                action=StrategyAction(
                    action_type=StrategyActionType.BUY_MARKET,
                    symbol="NIFTY",
                    quantity=1,
                    description="Buy NIFTY on EMA crossover"
                ),
                description="Buy action on crossover"
            ),
            StrategyStep(
                step_id="step_3",
                step_type=StrategyStepType.CONDITION,
                step_order=2,
                condition=StrategyCondition(
                    condition_type=StrategyConditionType.EMA_CROSSES_BELOW,
                    symbol="NIFTY",
                    value=0,
                    description="Check if short EMA crosses below long EMA"
                ),
                description="Check reverse crossover"
            ),
            StrategyStep(
                step_id="step_4",
                step_type=StrategyStepType.ACTION,
                step_order=3,
                action=StrategyAction(
                    action_type=StrategyActionType.SELL_MARKET,
                    symbol="NIFTY",
                    quantity=1,
                    description="Sell NIFTY on reverse crossover"
                ),
                description="Sell action on reverse crossover"
            )
        ]
    )
    
    try:
        # Create the strategy
        strategy = await create_strategy(strategy_data, "test_user_id")
        print(f"✅ Strategy created successfully: {strategy.name} (ID: {strategy.id})")
        print(f"   Steps: {len(strategy.steps)}")
        print(f"   Status: {strategy.status}")
        print(f"   Symbols: {strategy.symbols}")
        
        return strategy.id
        
    except Exception as e:
        print(f"❌ Error creating strategy: {e}")
        return None

async def test_strategy_retrieval():
    """Test retrieving strategies"""
    print("\n=== Testing Strategy Retrieval ===")
    
    try:
        # Get all strategies
        strategies = await get_strategies()
        print(f"✅ Retrieved {len(strategies)} strategies")
        
        for strategy in strategies:
            print(f"   - {strategy.name} (ID: {strategy.id}, Status: {strategy.status})")
        
        return strategies
        
    except Exception as e:
        print(f"❌ Error retrieving strategies: {e}")
        return []

async def test_strategy_update(strategy_id):
    """Test updating a strategy"""
    print(f"\n=== Testing Strategy Update (ID: {strategy_id}) ===")
    
    try:
        # Get the strategy first
        strategy = await get_strategy_by_id(strategy_id)
        if not strategy:
            print(f"❌ Strategy not found: {strategy_id}")
            return False
        
        # Update the strategy
        from models import StrategyUpdate
        update_data = StrategyUpdate(
            description="Updated EMA Crossover Strategy with better risk management",
            risk_per_trade=1.5
        )
        
        updated_strategy = await update_strategy(strategy_id, update_data)
        if updated_strategy:
            print(f"✅ Strategy updated successfully")
            print(f"   New description: {updated_strategy.description}")
            print(f"   New risk per trade: {updated_strategy.risk_per_trade}%")
            return True
        else:
            print(f"❌ Failed to update strategy")
            return False
            
    except Exception as e:
        print(f"❌ Error updating strategy: {e}")
        return False

async def test_strategy_deletion(strategy_id):
    """Test deleting a strategy"""
    print(f"\n=== Testing Strategy Deletion (ID: {strategy_id}) ===")
    
    try:
        # Delete the strategy
        success = await delete_strategy(strategy_id)
        if success:
            print(f"✅ Strategy deleted successfully")
            
            # Verify deletion
            strategy = await get_strategy_by_id(strategy_id)
            if not strategy:
                print(f"✅ Strategy deletion verified")
                return True
            else:
                print(f"❌ Strategy still exists after deletion")
                return False
        else:
            print(f"❌ Failed to delete strategy")
            return False
            
    except Exception as e:
        print(f"❌ Error deleting strategy: {e}")
        return False

async def test_complex_strategy():
    """Test creating a more complex strategy with multiple conditions and actions"""
    print("\n=== Testing Complex Strategy Creation ===")
    
    strategy_data = StrategyCreate(
        name="Multi-Condition Strategy",
        description="Complex strategy with multiple conditions and actions",
        status=StrategyStatus.DRAFT,
        symbols=["NIFTY", "BANKNIFTY"],
        max_positions=5,
        risk_per_trade=1.0,
        is_active=True,
        steps=[
            # Wait for market open
            StrategyStep(
                step_id="wait_market_open",
                step_type=StrategyStepType.CONDITION,
                step_order=0,
                condition=StrategyCondition(
                    condition_type=StrategyConditionType.TIME_AFTER,
                    time_value="09:15:00",
                    value=0,
                    description="Wait for market open"
                ),
                description="Wait for market to open"
            ),
            # Check if NIFTY price is above EMA
            StrategyStep(
                step_id="check_nifty_ema",
                step_type=StrategyStepType.CONDITION,
                step_order=1,
                condition=StrategyCondition(
                    condition_type=StrategyConditionType.PRICE_ABOVE,
                    symbol="NIFTY",
                    value=25000,
                    description="Check if NIFTY is above 25000"
                ),
                description="Check NIFTY price condition"
            ),
            # Buy NIFTY
            StrategyStep(
                step_id="buy_nifty",
                step_type=StrategyStepType.ACTION,
                step_order=2,
                action=StrategyAction(
                    action_type=StrategyActionType.BUY_MARKET,
                    symbol="NIFTY",
                    quantity=1,
                    stop_loss=24800,
                    take_profit=25200,
                    description="Buy NIFTY with stop loss and take profit"
                ),
                description="Buy NIFTY position"
            ),
            # Wait for some time
            StrategyStep(
                step_id="wait_time",
                step_type=StrategyStepType.ACTION,
                step_order=3,
                action=StrategyAction(
                    action_type=StrategyActionType.WAIT,
                    wait_seconds=300,  # 5 minutes
                    description="Wait for 5 minutes"
                ),
                description="Wait before next action"
            ),
            # Check if BANKNIFTY is also above threshold
            StrategyStep(
                step_id="check_banknifty",
                step_type=StrategyStepType.CONDITION,
                step_order=4,
                condition=StrategyCondition(
                    condition_type=StrategyConditionType.PRICE_ABOVE,
                    symbol="BANKNIFTY",
                    value=45000,
                    description="Check if BANKNIFTY is above 45000"
                ),
                description="Check BANKNIFTY condition"
            ),
            # Buy BANKNIFTY
            StrategyStep(
                step_id="buy_banknifty",
                step_type=StrategyStepType.ACTION,
                step_order=5,
                action=StrategyAction(
                    action_type=StrategyActionType.BUY_MARKET,
                    symbol="BANKNIFTY",
                    quantity=1,
                    stop_loss=44800,
                    take_profit=45200,
                    description="Buy BANKNIFTY with stop loss and take profit"
                ),
                description="Buy BANKNIFTY position"
            )
        ]
    )
    
    try:
        strategy = await create_strategy(strategy_data, "test_user_id")
        print(f"✅ Complex strategy created successfully: {strategy.name}")
        print(f"   Steps: {len(strategy.steps)}")
        print(f"   Symbols: {strategy.symbols}")
        print(f"   Max positions: {strategy.max_positions}")
        
        # Print step details
        for i, step in enumerate(strategy.steps):
            print(f"   Step {i+1}: {step.step_type} - {step.description}")
            if step.condition:
                print(f"     Condition: {step.condition.condition_type} ({step.condition.symbol})")
            if step.action:
                print(f"     Action: {step.action.action_type} ({step.action.symbol})")
        
        return strategy.id
        
    except Exception as e:
        print(f"❌ Error creating complex strategy: {e}")
        return None

async def main():
    """Main test function"""
    print("🚀 Starting Strategy Module Tests")
    print("=" * 50)
    
    # Connect to database
    await connect_to_mongo()
    
    try:
        # Test 1: Create simple strategy
        strategy_id = await test_strategy_creation()
        
        # Test 2: Retrieve strategies
        strategies = await test_strategy_retrieval()
        
        # Test 3: Update strategy
        if strategy_id:
            await test_strategy_update(strategy_id)
        
        # Test 4: Create complex strategy
        complex_strategy_id = await test_complex_strategy()
        
        # Test 5: Delete simple strategy
        if strategy_id:
            await test_strategy_deletion(strategy_id)
        
        print("\n" + "=" * 50)
        print("✅ All tests completed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        
    finally:
        # Close database connection
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main()) 